import { describe, it, expect, beforeEach, vi } from "vitest";
import {
  getAuthToken,
  setAuthToken,
  getStoredUser,
  getRuntimeConfig,
  ApiError,
} from "@/lib/api";

describe("API Client & Auth Layer", () => {
  beforeEach(() => {
    localStorage.clear();
    vi.restoreAllMocks();
  });

  it("stores and retrieves auth tokens and user attributes", () => {
    setAuthToken("jwt-token-123", "student@cloudtrain.dev", "user-uuid-456");
    expect(getAuthToken()).toBe("jwt-token-123");

    const user = getStoredUser();
    expect(user.email).toBe("student@cloudtrain.dev");
    expect(user.userId).toBe("user-uuid-456");

    setAuthToken(null);
    expect(getAuthToken()).toBe("mock-token");
  });

  it("loads runtime configuration from /config.json", async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({
        api_url: "https://api.cloudtrain.aws",
        region: "ap-south-1",
        user_pool_id: "pool-123",
        user_pool_client_id: "client-456",
      }),
    });

    const config = await getRuntimeConfig();
    expect(config.api_url).toBe("https://api.cloudtrain.aws");
    expect(config.region).toBe("ap-south-1");
  });

  it("constructs ApiError with HTTP status, error code, and field errors", () => {
    const err = new ApiError(400, "Validation failed", "INVALID_INPUT", [
      { path: "model.hyperparameters.n_estimators", message: "Must be >= 10" },
    ]);
    expect(err.status).toBe(400);
    expect(err.code).toBe("INVALID_INPUT");
    expect(err.fields?.[0].path).toBe("model.hyperparameters.n_estimators");
  });
});
