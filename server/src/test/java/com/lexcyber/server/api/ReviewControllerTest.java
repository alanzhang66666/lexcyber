package com.lexcyber.server.api;

import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.ArgumentMatchers.isNull;
import static org.mockito.Mockito.doReturn;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.post;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.jsonPath;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.SerializationFeature;
import com.lexcyber.server.auth.AuthAccount;
import com.lexcyber.server.auth.AuthService;
import com.lexcyber.server.review.ReviewIdentity;
import com.lexcyber.server.review.ReviewService;
import java.util.List;
import java.util.Map;
import java.util.UUID;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.extension.ExtendWith;
import org.mockito.Mock;
import org.mockito.junit.jupiter.MockitoExtension;
import org.springframework.http.HttpStatus;
import org.springframework.http.MediaType;
import org.springframework.http.converter.json.MappingJackson2HttpMessageConverter;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;
import org.springframework.validation.beanvalidation.LocalValidatorFactoryBean;
import org.springframework.web.server.ResponseStatusException;

@ExtendWith(MockitoExtension.class)
class ReviewControllerTest {
    @Mock
    ReviewService reviews;
    @Mock
    ReviewIdentity identity;
    @Mock
    AuthService auth;
    MockMvc mvc;

    private final AuthAccount owner = new AuthAccount(UUID.randomUUID(), "alice", "Alice");
    private final UUID reviewId = UUID.fromString("11111111-1111-4111-8111-111111111111");

    @BeforeEach
    void setup() {
        LocalValidatorFactoryBean validator = new LocalValidatorFactoryBean();
        validator.afterPropertiesSet();
        ObjectMapper mapper = new ObjectMapper().findAndRegisterModules()
                .disable(SerializationFeature.WRITE_DATES_AS_TIMESTAMPS);
        mvc = MockMvcBuilders.standaloneSetup(new ReviewController(reviews, identity, auth))
                .setControllerAdvice(new ApiExceptionHandler())
                .setValidator(validator)
                .setMessageConverters(new MappingJackson2HttpMessageConverter(mapper))
                .build();
    }

    @Test
    void unauthenticatedListDoesNotDumpReviews() throws Exception {
        when(auth.require(isNull())).thenThrow(new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session required"));
        mvc.perform(get("/v1/reviews?status=pending"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
        verify(reviews, never()).list(any(), any(), any(Integer.class), any(Integer.class));
    }

    @Test
    void ownedListIncludesCaseId() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        when(reviews.list(eq(owner.id()), eq("pending"), eq(0), eq(20))).thenReturn(Map.of(
                "items", List.of(reviewPayload()),
                "page", 0,
                "size", 20,
                "total", 1L));
        mvc.perform(get("/v1/reviews?status=pending").header("Authorization", "Bearer token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.items[0].id").value(reviewId.toString()))
                .andExpect(jsonPath("$.items[0].caseId").value("case-demo-001"))
                .andExpect(jsonPath("$.total").value(1));
    }

    @Test
    void getRequiresBearerAndReturnsCaseId() throws Exception {
        when(auth.require(isNull())).thenThrow(new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session required"));
        mvc.perform(get("/v1/reviews/" + reviewId))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
        verify(reviews, never()).get(any(), any());

        doReturn(owner).when(auth).require(any());
        when(reviews.get(owner.id(), reviewId)).thenReturn(reviewPayload());
        mvc.perform(get("/v1/reviews/" + reviewId).header("Authorization", "Bearer token"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("case-demo-001"))
                .andExpect(jsonPath("$.resultVersion").value(1));
    }

    @Test
    void otherOwnerGetIs404() throws Exception {
        when(auth.require(any())).thenReturn(owner);
        when(reviews.get(owner.id(), reviewId))
                .thenThrow(new ApiException(HttpStatus.NOT_FOUND, "REVIEW_NOT_FOUND", "复核记录不存在或不可访问"));
        mvc.perform(get("/v1/reviews/" + reviewId).header("Authorization", "Bearer token"))
                .andExpect(status().isNotFound())
                .andExpect(jsonPath("$.code").value("REVIEW_NOT_FOUND"));
    }

    @Test
    void decideRequiresSessionAndKeepsOwnerScope() throws Exception {
        when(auth.require(isNull())).thenThrow(new ResponseStatusException(HttpStatus.UNAUTHORIZED, "session required"));
        mvc.perform(post("/v1/reviews/" + reviewId + "/approve")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"resultVersion\":1,\"comment\":\"ok\"}"))
                .andExpect(status().isUnauthorized())
                .andExpect(jsonPath("$.code").value("UNAUTHORIZED"));
        verify(reviews, never()).decide(any(), any(), any(), any(Integer.class), any(), any());

        doReturn(owner).when(auth).require(any());
        when(identity.require(any(), isNull())).thenReturn("alice");
        when(reviews.decide(eq(owner.id()), eq(reviewId), eq("approve"), eq(1), eq("alice"), eq("ok")))
                .thenReturn(reviewPayload());
        mvc.perform(post("/v1/reviews/" + reviewId + "/approve")
                        .header("Authorization", "Bearer token")
                        .contentType(MediaType.APPLICATION_JSON)
                        .content("{\"resultVersion\":1,\"comment\":\"ok\"}"))
                .andExpect(status().isOk())
                .andExpect(jsonPath("$.caseId").value("case-demo-001"));
    }

    private Map<String, Object> reviewPayload() {
        return Map.of(
                "id", reviewId,
                "taskId", UUID.fromString("22222222-2222-4222-8222-222222222222"),
                "caseId", "case-demo-001",
                "resultVersion", 1,
                "status", "pending",
                "decision", "none");
    }
}
