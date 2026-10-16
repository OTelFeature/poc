package otelfeature.poc;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.catchThrowableOfType;

import java.util.Map;

import org.junit.jupiter.api.AfterAll;
import org.junit.jupiter.api.BeforeAll;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.params.ParameterizedTest;
import org.junit.jupiter.params.provider.ValueSource;
import org.springframework.http.HttpStatus;
import org.springframework.web.server.ResponseStatusException;

import dev.openfeature.sdk.OpenFeatureAPI;
import dev.openfeature.sdk.providers.memory.Flag;
import dev.openfeature.sdk.providers.memory.InMemoryProvider;

/**
 * The value range of {@code weatherUpstreamFailure}: UC-006 BR-002 and A1/A2,
 * TC-005 item 7 (OTelFeature/poc#75). The bounds are deterministic (a share at
 * or above 1.0 beats every draw from [0, 1), one at or below 0.0 none), so
 * each case runs a batch of calls and expects all or none to fail.
 */
class FaultInjectionTest {

    private static final int CALLS = 1_000;

    private static FaultInjection faultInjection;

    @BeforeAll
    static void setUp() {
        // The constructor sets a flagd provider; nothing listens on port 1.
        // Each test replaces it with an in-memory provider on the same API.
        faultInjection = new FaultInjection("localhost", 1);
    }

    @AfterAll
    static void tearDown() {
        faultInjection.shutdown();
    }

    private static void flag(Flag<?> flag) {
        OpenFeatureAPI.getInstance().setProviderAndWait(
                new InMemoryProvider(Map.of(FaultInjection.FLAG, flag)));
    }

    private static void share(double value) {
        flag(Flag.<Double>builder().variant("v", value).defaultVariant("v").build());
    }

    private static int failures() {
        int failed = 0;
        for (int i = 0; i < CALLS; i++) {
            ResponseStatusException e = catchThrowableOfType(
                    ResponseStatusException.class, faultInjection::maybeFail);
            if (e != null) {
                // A2 flow step 3: the injected 503 is the only exception.
                assertThat(e.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
                failed++;
            }
        }
        return failed;
    }

    @ParameterizedTest(name = "{0} fails every request")
    @ValueSource(doubles = {1.0, 1.5, 100.0, Double.POSITIVE_INFINITY})
    void atOrAboveOneFailsEveryRequest(double value) {
        share(value);
        assertThat(failures()).isEqualTo(CALLS);
    }

    @ParameterizedTest(name = "{0} fails no request")
    @ValueSource(doubles = {0.0, -0.0, -0.5, -100.0, Double.NEGATIVE_INFINITY, Double.NaN})
    void atOrBelowZeroOrNaNFailsNoRequest(double value) {
        share(value);
        assertThat(failures()).isZero();
    }

    // Non-numbers: the OpenFeature client's type check returns the default
    // 0.0 (UC-006 A2), checked here through the SDK's in-memory provider.
    @Test
    void stringIsATypeMismatchAndFailsNoRequest() {
        flag(Flag.<String>builder().variant("v", "1.0").defaultVariant("v").build());
        assertThat(failures()).isZero();
    }

    @Test
    void booleanIsATypeMismatchAndFailsNoRequest() {
        flag(Flag.<Boolean>builder().variant("v", true).defaultVariant("v").build());
        assertThat(failures()).isZero();
    }

    @Test
    void missingFlagFailsNoRequest() {
        OpenFeatureAPI.getInstance().setProviderAndWait(new InMemoryProvider(Map.of()));
        assertThat(failures()).isZero();
    }
}
