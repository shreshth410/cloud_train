import { describe, it, expect, vi } from "vitest";
import { render, screen, fireEvent } from "@testing-library/react";
import { BrowserRouter } from "react-router-dom";
import { QueryClient, QueryClientProvider } from "@tanstack/react-query";
import { Wizard } from "@/pages/Wizard";
import * as api from "@/lib/api";

const mockDatasets = [
  {
    dataset_id: "ds-iris-123",
    user_id: "u-1",
    name: "Iris Flowers",
    filename: "iris.csv",
    size_bytes: 4500,
    status: "READY" as const,
    profile: {
      row_count: 150,
      column_count: 5,
      columns: [
        {
          name: "sepal_length",
          dtype: "float64",
          inferred_type: "numeric" as const,
          missing_count: 0,
          missing_pct: 0,
          unique_count: 35,
        },
        {
          name: "target",
          dtype: "int64",
          inferred_type: "categorical" as const,
          missing_count: 0,
          missing_pct: 0,
          unique_count: 3,
        },
      ],
      preview: [],
      warnings: [],
    },
    created_at: new Date().toISOString(),
    updated_at: new Date().toISOString(),
  },
];

const mockModels = [
  {
    id: "random_forest",
    name: "Random Forest",
    task: ["classification" as const, "regression" as const],
    description: "Ensemble of decision trees.",
    needs_scaling: false,
    recommended: true,
    hyperparameters: {
      n_estimators: {
        type: "int" as const,
        default: 100,
        min: 10,
        max: 500,
        description: "Number of trees.",
      },
    },
  },
];

describe("Wizard Component & Validation", () => {
  it("renders wizard step 1 and blocks Next when no dataset is selected", async () => {
    vi.spyOn(api, "fetchDatasets").mockResolvedValue(mockDatasets);
    vi.spyOn(api, "fetchModels").mockResolvedValue(mockModels);
    vi.spyOn(api, "fetchQuotas").mockResolvedValue({
      user_id: "u-1",
      datasets: { count: 1, max: 10 },
      active_jobs: { count: 0, max: 3 },
      total_jobs: { count: 1 },
    });

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Wizard />
        </BrowserRouter>
      </QueryClientProvider>
    );

    // Initial step is Dataset
    expect(await screen.findByText("Select a Dataset")).toBeInTheDocument();

    const nextButton = screen.getByRole("button", { name: /Next/i });
    fireEvent.click(nextButton);

    // Should display validation error
    expect(
      screen.getByText("Please select a dataset to continue.")
    ).toBeInTheDocument();
  });

  it("progresses to Target step when dataset is chosen", async () => {
    vi.spyOn(api, "fetchDatasets").mockResolvedValue(mockDatasets);
    vi.spyOn(api, "fetchModels").mockResolvedValue(mockModels);

    const queryClient = new QueryClient({
      defaultOptions: { queries: { retry: false } },
    });

    render(
      <QueryClientProvider client={queryClient}>
        <BrowserRouter>
          <Wizard />
        </BrowserRouter>
      </QueryClientProvider>
    );

    const datasetCard = await screen.findByText("Iris Flowers");
    fireEvent.click(datasetCard);

    const nextButton = screen.getByRole("button", { name: /Next/i });
    fireEvent.click(nextButton);

    // Step 2 Target should now be displayed
    expect(
      await screen.findByText("Select Prediction Target")
    ).toBeInTheDocument();
  });
});
