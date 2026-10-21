import { beforeEach, describe, expect, it, vi } from "vitest";

beforeEach(() => { vi.resetModules(); vi.restoreAllMocks(); });

async function clientWith(payload: unknown) {
  global.fetch = vi.fn()
    .mockResolvedValueOnce({ ok: true, json: async () => ({ api_url: "/api" }) })
    .mockResolvedValue({ ok: true, status: 200, headers: new Headers({ "Content-Type": "application/json" }), json: async () => payload });
  return import("@/lib/api");
}

describe("Backend response contracts", () => {
  it("maps registry fields into wizard models", async () => {
    const api = await clientWith({ models: [{ id: "ridge", display_name: "Ridge", tasks: ["regression"], hyperparameters: [{ name: "alpha", type: "float", default: 1 }] }] });
    const [model] = await api.fetchModels();
    expect(model.name).toBe("Ridge");
    expect(model.task).toEqual(["regression"]);
    expect(model.hyperparameters.alpha.default).toBe(1);
  });
  it("maps profiles, preview rows and invalid-file reasons", async () => {
    const api = await clientWith({ dataset_id: "d", errors: ["Bad CSV"], profile: { columns: [{ name: "x", dtype: "numeric", missing_pct: 8 }], preview_rows: [["1"]], warnings: ["Missing values"] } });
    const dataset = await api.fetchDataset("d");
    expect(dataset.profile?.columns[0].inferred_type).toBe("numeric");
    expect(dataset.profile?.columns[0].missing_pct).toBe(.08);
    expect(dataset.profile?.preview).toEqual([{ x: "1" }]);
    expect(dataset.profile?.warnings[0].message).toBe("Missing values");
    expect(dataset.error?.message).toBe("Bad CSV");
  });
  it("maps download filenames to the download buttons", async () => {
    const api = await clientWith({ files: [{ name: "model.joblib", url: "http://localhost/model" }] });
    expect((await api.fetchJobArtifacts("j")).model_joblib).toBe("http://localhost/model");
  });
  it("renders backend log lines", async () => {
    const api = await clientWith({ lines: [{ text: "Training" }, { text: "Done" }], source: "s3" });
    expect((await api.fetchJobLogs("j")).logs).toBe("Training\nDone");
  });
  it("sends compute settings using the API schema", async () => {
    const api = await clientWith({ job_id: "j", status: "QUEUED" });
    await api.createJob({ dataset_id: "d", target_column: "target", model: { id: "ridge", hyperparameters: {} }, compute_size: "medium" });
    const options = vi.mocked(fetch).mock.calls[1][1];
    const sent = JSON.parse(options?.body as string);
    expect(sent.compute).toEqual({ size: "medium" });
    expect(sent).not.toHaveProperty("compute_size");
  });
  it("maps classification metrics and confusion matrix labels", async () => {
    const api = await clientWith({ metrics: { task: "classification", accuracy: .95, train_rows: 120, test_rows: 30, confusion_matrix: { classes: ["a"], matrix: [[30]] } }, feature_importance: { top_features: [{ feature: "x", importance: 1 }] } });
    const result = await api.fetchJobResults("j");
    expect(result.task).toBe("classification");
    expect(result.metrics.accuracy).toBe(.95);
    expect(result.confusion_matrix?.labels).toEqual(["a"]);
    expect(result.feature_importance?.features).toHaveLength(1);
  });
});
