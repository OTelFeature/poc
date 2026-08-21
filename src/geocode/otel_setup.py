"""Hand-rolled telemetry bootstrap, replacing `opentelemetry-instrument`.

Building this by hand (instead of the zero-code `opentelemetry-instrument`
launcher) is what makes `_VerbosityAwareTracerProvider` possible: it needs to
sit between the instrumentation libraries and the real SDK `TracerProvider`,
which the zero-code launcher gives no hook for.
"""

from __future__ import annotations

from contextlib import contextmanager
from typing import Iterator

from openfeature import api as feature_api
from openfeature.contrib.provider.flagd import FlagdProvider
from openfeature.contrib.provider.flagd.config import ResolverType
from opentelemetry import metrics, trace
from opentelemetry.context import Context
from opentelemetry.exporter.otlp.proto.http.metric_exporter import OTLPMetricExporter
from opentelemetry.exporter.otlp.proto.http.trace_exporter import OTLPSpanExporter
from opentelemetry.sdk.metrics import MeterProvider
from opentelemetry.sdk.metrics.export import PeriodicExportingMetricReader
from opentelemetry.sdk.resources import Resource
from opentelemetry.sdk.trace import TracerProvider as SDKTracerProvider
from opentelemetry.sdk.trace.export import BatchSpanProcessor
from opentelemetry.trace import Link, Span, SpanKind, Tracer, TracerProvider
from opentelemetry.util import types as otel_types

TRACE_VERBOSITY_FLAG_KEY = "telemetryLevel"
VERBOSITY_FULL = "FULL"
VERBOSITY_IO = "IO"


def _current_verbosity() -> str:
    # Evaluated fresh on every span. With the flagd provider in "in-process"
    # mode, this is an in-memory lookup against a ruleset flagd streams to us
    # and keeps updated in the background - no network call per span, and a
    # flag change in flagd takes effect on the very next span with no restart.
    client = feature_api.get_client()
    return client.get_string_value(TRACE_VERBOSITY_FLAG_KEY, VERBOSITY_FULL).strip().upper()


class _VerbosityAwareTracer(Tracer):
    """Wraps a real `Tracer`.

    When verbosity is `IO`, spans of kind `INTERNAL` are never created and
    never attached to context - `start_span`/`start_as_current_span` just
    hand back whatever span was already current. Anything created "under" a
    suppressed span therefore attaches directly to its real parent instead of
    to the suppressed span, so no orphaned parent references are produced.
    """

    def __init__(self, wrapped: Tracer) -> None:
        self._wrapped = wrapped

    @staticmethod
    def _suppress(kind: SpanKind) -> bool:
        return kind is SpanKind.INTERNAL and _current_verbosity() == VERBOSITY_IO

    def start_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: list[Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
    ) -> Span:
        if self._suppress(kind):
            return trace.get_current_span(context)
        return self._wrapped.start_span(
            name,
            context,
            kind,
            attributes,
            links,
            start_time,
            record_exception,
            set_status_on_exception,
        )

    @contextmanager
    def start_as_current_span(
        self,
        name: str,
        context: Context | None = None,
        kind: SpanKind = SpanKind.INTERNAL,
        attributes: otel_types.Attributes = None,
        links: list[Link] | None = None,
        start_time: int | None = None,
        record_exception: bool = True,
        set_status_on_exception: bool = True,
        end_on_exit: bool = True,
    ) -> Iterator[Span]:
        if self._suppress(kind):
            yield trace.get_current_span(context)
            return
        with self._wrapped.start_as_current_span(
            name,
            context,
            kind,
            attributes,
            links,
            start_time,
            record_exception,
            set_status_on_exception,
            end_on_exit,
        ) as span:
            yield span


class _VerbosityAwareTracerProvider(TracerProvider):
    """Wraps a real `TracerProvider`, handing out `_VerbosityAwareTracer`s."""

    def __init__(self, wrapped: TracerProvider) -> None:
        self._wrapped = wrapped

    def get_tracer(
        self,
        instrumenting_module_name: str,
        instrumenting_library_version: str | None = None,
        schema_url: str | None = None,
        attributes: otel_types.Attributes | None = None,
    ) -> Tracer:
        real_tracer = self._wrapped.get_tracer(
            instrumenting_module_name,
            instrumenting_library_version,
            schema_url,
            attributes,
        )
        return _VerbosityAwareTracer(real_tracer)


def configure_telemetry() -> None:
    """Sets up tracing (verbosity-aware) and metrics, and installs both
    globally - the same shape `opentelemetry-instrument` would set up, minus
    the parts (config file support, log correlation, ...) this PoC doesn't
    exercise. Also registers the flagd provider backing `_current_verbosity`.

    `FlagdProvider` reads its connection details (`FLAGD_HOST`, `FLAGD_PORT`,
    ...) from the environment; only the resolver type is fixed here, since
    `in-process` is a correctness requirement for the per-span read above,
    not something a deployment should be able to override.
    """
    feature_api.set_provider(FlagdProvider(resolver_type=ResolverType.IN_PROCESS))

    resource = Resource.create()

    tracer_provider = SDKTracerProvider(resource=resource)
    tracer_provider.add_span_processor(BatchSpanProcessor(OTLPSpanExporter()))
    trace.set_tracer_provider(_VerbosityAwareTracerProvider(tracer_provider))

    meter_provider = MeterProvider(
        resource=resource,
        metric_readers=[PeriodicExportingMetricReader(OTLPMetricExporter())],
    )
    metrics.set_meter_provider(meter_provider)
