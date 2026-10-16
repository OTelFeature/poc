package otelfeature.poc;

import java.util.concurrent.ThreadLocalRandom;

import org.slf4j.Logger;
import org.slf4j.LoggerFactory;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.http.HttpStatus;
import org.springframework.stereotype.Component;
import org.springframework.web.server.ResponseStatusException;

import dev.openfeature.contrib.hooks.otel.TracesHook;
import dev.openfeature.contrib.providers.flagd.Config;
import dev.openfeature.contrib.providers.flagd.FlagdOptions;
import dev.openfeature.contrib.providers.flagd.FlagdProvider;
import dev.openfeature.sdk.Client;
import dev.openfeature.sdk.OpenFeatureAPI;
import jakarta.annotation.PreDestroy;

/**
 * Fails a share of requests on demand, like the OTel Demo's fault-injection
 * flags (OTelFeature/poc#28).
 *
 * <p>The share comes from the number flag {@code weatherUpstreamFailure}
 * (0.0 to 1.0), evaluated by the application's own OpenFeature client. This
 * is a separate OpenFeature API instance from the one inside the agent
 * extension, which only decides about spans; this one is ordinary
 * application code, the way any service would use feature flags.
 *
 * <p>Same flagd, same in-process resolver (gRPC sync on {@code FLAGD_PORT}),
 * so a flip in {@code flagd.json} applies to the next request. Until flagd is
 * reachable, or if the flag is missing, the share is 0: nothing fails.
 */
@Component
public class FaultInjection {

    static final String FLAG = "weatherUpstreamFailure";

    private static final Logger log = LoggerFactory.getLogger(FaultInjection.class);

    private final OpenFeatureAPI api = OpenFeatureAPI.getInstance();
    private final Client client;

    public FaultInjection(@Value("${FLAGD_HOST:localhost}") String host,
                          @Value("${FLAGD_PORT:8015}") int port) {
        // Non-blocking: the app starts even if flagd is down, and evaluations
        // return the default (no failures) until the provider is ready.
        api.setProvider(new FlagdProvider(FlagdOptions.builder()
                .resolverType(Config.Resolver.IN_PROCESS)
                .host(host)
                .port(port)
                .build()));
        this.client = api.getClient("weather");
        // Records each evaluation as a span event on the current span (the
        // request's), so a failed trace shows which flag failed it (UC-007).
        // On this client only: the agent extension's evaluations live in its
        // own, isolated OpenFeature API and stay unrecorded.
        this.client.addHooks(new TracesHook());
    }

    /**
     * Throws HTTP 503 for the configured share of calls, as if the upstream
     * weather API had failed.
     */
    public void maybeFail() {
        double share = client.getDoubleValue(FLAG, 0.0);
        if (share > 0.0 && ThreadLocalRandom.current().nextDouble() < share) {
            log.debug("Injecting upstream failure ({}={})", FLAG, share);
            throw new ResponseStatusException(HttpStatus.SERVICE_UNAVAILABLE,
                    "Injected upstream failure (" + FLAG + "=" + share + ")");
        }
    }

    @PreDestroy
    void shutdown() {
        api.shutdown();
    }
}
