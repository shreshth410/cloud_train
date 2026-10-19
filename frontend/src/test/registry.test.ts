import { describe, it, expect } from "vitest";
import modelRegistry from "../../../shared/model_registry.json";

describe("Model Registry & Hyperparameter Specifications", () => {
  it("contains all expected models from Section 12", () => {
    const ids = modelRegistry.models.map((m) => m.id);
    expect(ids).toContain("logistic_regression");
    expect(ids).toContain("linear_regression");
    expect(ids).toContain("ridge");
    expect(ids).toContain("decision_tree");
    expect(ids).toContain("random_forest");
    expect(ids).toContain("xgboost");
    expect(ids).toContain("knn");
  });

  it("verifies hyperparameters adhere to strict types and default values", () => {
    modelRegistry.models.forEach((model) => {
      model.hyperparameters.forEach((param) => {
        const hp = param as any;
        expect(["int", "float", "str", "bool", "enum"]).toContain(hp.type);
        if (hp.type === "int" || hp.type === "float") {
          if (hp.default !== null) {
            expect(typeof hp.default).toBe("number");
            if (hp.min !== undefined) expect(hp.default).toBeGreaterThanOrEqual(hp.min);
            if (hp.max !== undefined) expect(hp.default).toBeLessThanOrEqual(hp.max);
          }
        }
        if (hp.type === "enum") {
          expect(Array.isArray(hp.options)).toBe(true);
          if (hp.default !== null) {
            expect(hp.options).toContain(hp.default);
          } else {
            expect(hp.nullable).toBe(true);
          }
        }
      });
    });
  });

  it("ensures models specify classification or regression tasks correctly", () => {
    const rf = modelRegistry.models.find((m) => m.id === "random_forest");
    expect(rf).toBeDefined();
    expect(rf?.tasks).toContain("classification");
    expect(rf?.tasks).toContain("regression");

    const lr = modelRegistry.models.find((m) => m.id === "linear_regression");
    expect(lr?.tasks).toEqual(["regression"]);

    const logr = modelRegistry.models.find((m) => m.id === "logistic_regression");
    expect(logr?.tasks).toEqual(["classification"]);
  });
});
