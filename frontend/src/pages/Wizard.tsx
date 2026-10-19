import React, { useState, useEffect } from "react";
import { useNavigate, useSearchParams } from "react-router-dom";
import { useQuery } from "@tanstack/react-query";
import {
  fetchDatasets,
  fetchModels,
  fetchQuotas,
  createJob,
  ApiError,
} from "@/lib/api";
import {
  ModelMetadata,
  TaskType,
  ComputeSize,
  JobConfig,
} from "@/types";
import { formatBytes } from "@/utils/formatters";
import {
  Sparkles,
  ArrowRight,
  ArrowLeft,
  CheckCircle2,
  AlertCircle,
  Cpu,
  Layers,
  Database,
  Sliders,
  FileCheck,
  Check,
  RotateCcw,
  ChevronDown,
  ChevronUp,
} from "lucide-react";

const STEPS = [
  { id: 1, name: "Dataset", icon: Database },
  { id: 2, name: "Target", icon: Layers },
  { id: 3, name: "Features", icon: CheckCircle2 },
  { id: 4, name: "Model", icon: Sparkles },
  { id: 5, name: "Hyperparameters", icon: Sliders },
  { id: 6, name: "Compute", icon: Cpu },
  { id: 7, name: "Review & Train", icon: FileCheck },
];

export const Wizard: React.FC = () => {
  const navigate = useNavigate();
  const [searchParams] = useSearchParams();

  // Load datasets, models, and quotas
  const { data: datasets = [], isLoading: loadingDatasets } = useQuery({
    queryKey: ["datasets"],
    queryFn: fetchDatasets,
  });

  const { data: models = [], isLoading: loadingModels } = useQuery({
    queryKey: ["models"],
    queryFn: fetchModels,
  });

  const { data: quotas } = useQuery({
    queryKey: ["quotas"],
    queryFn: fetchQuotas,
  });

  // State management with sessionStorage persistence
  const [currentStep, setCurrentStep] = useState<number>(() => {
    const saved = sessionStorage.getItem("cloudtrain_wizard_step");
    return saved ? parseInt(saved, 10) : 1;
  });

  const [selectedDatasetId, setSelectedDatasetId] = useState<string>(() => {
    return (
      searchParams.get("dataset") ||
      sessionStorage.getItem("cloudtrain_wizard_dataset") ||
      ""
    );
  });

  const [targetColumn, setTargetColumn] = useState<string>(() => {
    return sessionStorage.getItem("cloudtrain_wizard_target") || "";
  });

  const [taskType, setTaskType] = useState<TaskType>(() => {
    return (
      (sessionStorage.getItem("cloudtrain_wizard_task") as TaskType) ||
      "classification"
    );
  });

  const [selectedFeatures, setSelectedFeatures] = useState<string[]>(() => {
    const saved = sessionStorage.getItem("cloudtrain_wizard_features");
    return saved ? JSON.parse(saved) : [];
  });

  const [selectedModelId, setSelectedModelId] = useState<string>(() => {
    return sessionStorage.getItem("cloudtrain_wizard_model") || "random_forest";
  });

  const [hyperparameters, setHyperparameters] = useState<Record<string, any>>(() => {
    const saved = sessionStorage.getItem("cloudtrain_wizard_params");
    return saved ? JSON.parse(saved) : {};
  });

  const [computeSize, setComputeSize] = useState<ComputeSize>(() => {
    return (
      (sessionStorage.getItem("cloudtrain_wizard_compute") as ComputeSize) ||
      "small"
    );
  });

  const [jobName, setJobName] = useState<string>(() => {
    return sessionStorage.getItem("cloudtrain_wizard_name") || "";
  });

  // Advanced settings state
  const [showAdvanced, setShowAdvanced] = useState(false);
  const [testSize, setTestSize] = useState(0.2);
  const [cvFolds, setCvFolds] = useState(5);
  const [scaleNumeric, setScaleNumeric] = useState(true);
  const [numericImpute, setNumericImpute] = useState<"mean" | "median">("mean");
  const [dropIdLike, setDropIdLike] = useState(true);

  // Errors & submission
  const [stepError, setStepError] = useState<string | null>(null);
  const [serverErrors, setServerErrors] = useState<{ path: string; message: string }[]>(
    []
  );
  const [isSubmitting, setIsSubmitting] = useState(false);

  // Persist state to sessionStorage
  useEffect(() => {
    sessionStorage.setItem("cloudtrain_wizard_step", currentStep.toString());
    sessionStorage.setItem("cloudtrain_wizard_dataset", selectedDatasetId);
    sessionStorage.setItem("cloudtrain_wizard_target", targetColumn);
    sessionStorage.setItem("cloudtrain_wizard_task", taskType);
    sessionStorage.setItem(
      "cloudtrain_wizard_features",
      JSON.stringify(selectedFeatures)
    );
    sessionStorage.setItem("cloudtrain_wizard_model", selectedModelId);
    sessionStorage.setItem(
      "cloudtrain_wizard_params",
      JSON.stringify(hyperparameters)
    );
    sessionStorage.setItem("cloudtrain_wizard_compute", computeSize);
    sessionStorage.setItem("cloudtrain_wizard_name", jobName);
  }, [
    currentStep,
    selectedDatasetId,
    targetColumn,
    taskType,
    selectedFeatures,
    selectedModelId,
    hyperparameters,
    computeSize,
    jobName,
  ]);

  const selectedDataset = datasets.find((d) => d.dataset_id === selectedDatasetId);
  const readyDatasets = datasets.filter((d) => d.status === "READY");
  const selectedModel = models.find((m) => m.id === selectedModelId);

  // Automatically recommend compute size when dataset exceeds 20MB
  useEffect(() => {
    if (selectedDataset && selectedDataset.size_bytes > 20 * 1024 * 1024) {
      setComputeSize("medium");
    }
  }, [selectedDataset]);

  // When target changes, auto-detect task and auto-populate eligible features
  const handleTargetChange = (colName: string) => {
    setTargetColumn(colName);
    if (!selectedDataset?.profile) return;

    const col = selectedDataset.profile.columns.find((c) => c.name === colName);
    let detectedTask: TaskType = "classification";
    if (col) {
      if (col.inferred_type === "numeric" && col.unique_count > 10) {
        detectedTask = "regression";
      } else {
        detectedTask = "classification";
      }
    }
    setTaskType(detectedTask);

    // Filter features: exclude target and auto-excluded columns
    const eligibleFeatures = selectedDataset.profile.columns
      .filter((c) => {
        if (c.name === colName) return false;
        if (
          ["id_like", "constant", "text"].includes(c.inferred_type) ||
          c.missing_pct > 0.5
        ) {
          return false;
        }
        return true;
      })
      .map((c) => c.name);

    setSelectedFeatures(eligibleFeatures);

    // Pick first matching model for detected task
    const matchingModel = models.find((m) => m.task.includes(detectedTask));
    if (matchingModel) {
      setSelectedModelId(matchingModel.id);
      initDefaultsForModel(matchingModel);
    }
  };

  const initDefaultsForModel = (model: ModelMetadata) => {
    const defaults: Record<string, any> = {};
    Object.entries(model.hyperparameters).forEach(([key, def]) => {
      defaults[key] = def.default;
    });
    setHyperparameters(defaults);
  };

  // Step Validation
  const validateStep = (step: number): boolean => {
    setStepError(null);
    if (step === 1) {
      if (!selectedDatasetId) {
        setStepError("Please select a dataset to continue.");
        return false;
      }
    }
    if (step === 2) {
      if (!targetColumn) {
        setStepError("Please select a target column to predict.");
        return false;
      }
    }
    if (step === 3) {
      if (selectedFeatures.length === 0) {
        setStepError("Please select at least one feature column for training.");
        return false;
      }
    }
    if (step === 4) {
      if (!selectedModelId) {
        setStepError("Please select an ML algorithm.");
        return false;
      }
    }
    return true;
  };

  const nextStep = () => {
    if (validateStep(currentStep)) {
      if (currentStep === 6 && !jobName) {
        const dateStr = new Date().toISOString().slice(0, 10);
        const dsName = selectedDataset?.name || "Dataset";
        const modelName = selectedModel?.name || selectedModelId;
        setJobName(`${dsName} · ${modelName} · ${dateStr}`);
      }
      setCurrentStep((prev) => Math.min(STEPS.length, prev + 1));
    }
  };

  const prevStep = () => {
    setStepError(null);
    setCurrentStep((prev) => Math.max(1, prev - 1));
  };

  const handleLaunchTraining = async () => {
    setServerErrors([]);
    setIsSubmitting(true);
    try {
      const config: JobConfig = {
        name: jobName,
        dataset_id: selectedDatasetId,
        target_column: targetColumn,
        task: taskType,
        feature_columns: selectedFeatures,
        model: {
          id: selectedModelId,
          hyperparameters,
        },
        compute_size: computeSize,
        preprocessing: {
          numeric_impute: numericImpute,
          scale_numeric: scaleNumeric,
          drop_id_like: dropIdLike,
        },
        split: {
          test_size: testSize,
          stratify: taskType === "classification",
        },
        cross_validation: {
          folds: cvFolds,
        },
      };

      const res = await createJob(config);

      // Clear wizard session storage upon successful creation
      sessionStorage.removeItem("cloudtrain_wizard_step");
      sessionStorage.removeItem("cloudtrain_wizard_dataset");
      sessionStorage.removeItem("cloudtrain_wizard_target");
      sessionStorage.removeItem("cloudtrain_wizard_task");
      sessionStorage.removeItem("cloudtrain_wizard_features");
      sessionStorage.removeItem("cloudtrain_wizard_params");
      sessionStorage.removeItem("cloudtrain_wizard_name");

      navigate(`/jobs/${res.job_id}`);
    } catch (err: any) {
      if (err instanceof ApiError && err.fields) {
        setServerErrors(err.fields);
      } else {
        setStepError(err.message || "Failed to submit training job.");
      }
      setIsSubmitting(false);
    }
  };

  return (
    <div className="space-y-8 max-w-5xl mx-auto">
      {/* Stepper Progress Header */}
      <div className="p-4 rounded-2xl glass-panel">
        <div className="flex items-center justify-between overflow-x-auto py-2 px-1">
          {STEPS.map((step, idx) => {
            const Icon = step.icon;
            const isCompleted = currentStep > step.id;
            const isCurrent = currentStep === step.id;
            return (
              <React.Fragment key={step.id}>
                <button
                  type="button"
                  onClick={() => {
                    if (isCompleted) setCurrentStep(step.id);
                  }}
                  disabled={!isCompleted && !isCurrent}
                  className={`flex items-center gap-2 text-xs font-medium transition-all ${
                    isCurrent
                      ? "text-cyan-400 font-semibold"
                      : isCompleted
                      ? "text-slate-300 hover:text-white cursor-pointer"
                      : "text-slate-600 cursor-not-allowed"
                  }`}
                >
                  <div
                    className={`w-7 h-7 rounded-full flex items-center justify-center text-xs border ${
                      isCurrent
                        ? "bg-cyan-500/20 border-cyan-400 text-cyan-300 shadow-md shadow-cyan-500/30"
                        : isCompleted
                        ? "bg-emerald-950/60 border-emerald-500 text-emerald-400"
                        : "bg-slate-900 border-slate-800 text-slate-500"
                    }`}
                  >
                    {isCompleted ? <Check className="w-3.5 h-3.5" /> : step.id}
                  </div>
                  <span className="hidden sm:inline-flex items-center gap-1.5 whitespace-nowrap">
                    <Icon className="w-3.5 h-3.5 opacity-80" />
                    {step.name}
                  </span>
                </button>
                {idx < STEPS.length - 1 && (
                  <div
                    className={`flex-1 h-0.5 mx-2 min-w-[12px] transition-colors ${
                      currentStep > step.id ? "bg-emerald-500/60" : "bg-slate-800"
                    }`}
                  />
                )}
              </React.Fragment>
            );
          })}
        </div>
      </div>

      {/* Inline Error Alert */}
      {stepError && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 text-rose-300 text-sm flex items-center gap-3">
          <AlertCircle className="w-5 h-5 text-rose-400 flex-shrink-0" />
          <span>{stepError}</span>
        </div>
      )}

      {/* Server Validation Errors List */}
      {serverErrors.length > 0 && (
        <div className="p-4 rounded-xl bg-rose-950/40 border border-rose-800/60 space-y-2">
          <div className="text-sm font-semibold text-rose-300 flex items-center gap-2">
            <AlertCircle className="w-4 h-4 text-rose-400" />
            Validation Errors:
          </div>
          <ul className="text-xs text-rose-200 list-disc list-inside space-y-1">
            {serverErrors.map((f, i) => (
              <li key={i}>
                <span className="font-mono text-rose-300">{f.path}:</span> {f.message}
              </li>
            ))}
          </ul>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 1: DATASET SELECTION */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 1 && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white">Select a Dataset</h2>
            <p className="text-sm text-slate-400 mt-1">
              Choose from your profiled datasets ready for model training.
            </p>
          </div>

          {loadingDatasets ? (
            <div className="p-8 text-center text-slate-400">Loading datasets...</div>
          ) : readyDatasets.length === 0 ? (
            <div className="p-8 rounded-xl bg-slate-900/60 border border-slate-800 text-center space-y-3">
              <p className="text-sm text-slate-300">No ready datasets available.</p>
              <button
                onClick={() => navigate("/datasets")}
                className="px-4 py-2 rounded-lg bg-cyan-600 text-white text-xs font-medium"
              >
                Go to Datasets to Upload
              </button>
            </div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {readyDatasets.map((ds) => {
                const isSelected = selectedDatasetId === ds.dataset_id;
                return (
                  <div
                    key={ds.dataset_id}
                    onClick={() => {
                      setSelectedDatasetId(ds.dataset_id);
                      setStepError(null);
                    }}
                    className={`p-4 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? "border-cyan-500 bg-cyan-950/30 shadow-md shadow-cyan-500/10"
                        : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-start justify-between">
                      <div className="space-y-1">
                        <h4 className="font-semibold text-white">{ds.name}</h4>
                        <p className="text-xs text-slate-400 font-mono">
                          {ds.filename} • {formatBytes(ds.size_bytes)}
                        </p>
                      </div>
                      <div
                        className={`w-5 h-5 rounded-full border flex items-center justify-center ${
                          isSelected
                            ? "border-cyan-400 bg-cyan-500 text-black"
                            : "border-slate-700"
                        }`}
                      >
                        {isSelected && <Check className="w-3.5 h-3.5" />}
                      </div>
                    </div>
                    {ds.profile && (
                      <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center justify-between text-xs text-slate-400 font-mono">
                        <span>{ds.profile.row_count.toLocaleString()} rows</span>
                        <span>{ds.profile.column_count} columns</span>
                      </div>
                    )}
                  </div>
                );
              })}
            </div>
          )}
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 2: TARGET COLUMN */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 2 && selectedDataset && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white">Select Prediction Target</h2>
            <p className="text-sm text-slate-400 mt-1">
              Choose the column you want CloudTrain to predict or forecast.
            </p>
          </div>

          <div className="space-y-4 max-w-xl">
            <div>
              <label className="block text-xs font-medium text-slate-300 mb-1.5">
                Target Column
              </label>
              <select
                value={targetColumn}
                onChange={(e) => handleTargetChange(e.target.value)}
                className="w-full px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white text-sm focus:outline-none focus:border-cyan-500"
              >
                <option value="">— Select Target Column —</option>
                {selectedDataset.profile?.columns.map((c) => (
                  <option key={c.name} value={c.name}>
                    {c.name} ({c.inferred_type}, {c.unique_count} distinct)
                  </option>
                ))}
              </select>
            </div>

            {targetColumn && (
              <div className="p-4 rounded-xl bg-slate-900/80 border border-slate-800 space-y-3">
                <div className="flex items-center justify-between">
                  <span className="text-xs text-slate-400 uppercase font-medium">
                    Detected Machine Learning Task
                  </span>
                  <div className="flex items-center gap-2">
                    <span
                      className={`px-2 py-0.5 rounded text-xs font-semibold uppercase ${
                        taskType === "classification"
                          ? "bg-purple-950/60 text-purple-300 border border-purple-800/60"
                          : "bg-cyan-950/60 text-cyan-300 border border-cyan-800/60"
                      }`}
                    >
                      {taskType}
                    </span>
                    <button
                      type="button"
                      onClick={() =>
                        setTaskType((prev) =>
                          prev === "classification" ? "regression" : "classification"
                        )
                      }
                      className="text-xs text-cyan-400 underline hover:text-cyan-300"
                    >
                      Override
                    </button>
                  </div>
                </div>

                <p className="text-xs text-slate-300">
                  {taskType === "classification"
                    ? "Classification: Predicting discrete classes or categories (evaluating Accuracy, F1, ROC-AUC)."
                    : "Regression: Predicting continuous numeric values (evaluating R², MAE, RMSE)."}
                </p>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 3: FEATURES SELECTION */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 3 && selectedDataset && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div className="flex flex-col sm:flex-row sm:items-center justify-between gap-3">
            <div>
              <h2 className="text-xl font-bold text-white">Select Features</h2>
              <p className="text-sm text-slate-400 mt-1">
                Choose inputs for the model. Problematic columns have been pre-excluded with explanations.
              </p>
            </div>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  const allEligible =
                    selectedDataset.profile?.columns
                      .filter((c) => c.name !== targetColumn)
                      .map((c) => c.name) || [];
                  setSelectedFeatures(allEligible);
                }}
                className="text-xs px-2.5 py-1.5 rounded bg-slate-800 text-slate-300 hover:text-white"
              >
                Select All
              </button>
              <button
                type="button"
                onClick={() => setSelectedFeatures([])}
                className="text-xs px-2.5 py-1.5 rounded bg-slate-800 text-slate-300 hover:text-white"
              >
                Clear All
              </button>
            </div>
          </div>

          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-3 gap-3">
            {selectedDataset.profile?.columns
              .filter((c) => c.name !== targetColumn)
              .map((col) => {
                const isSelected = selectedFeatures.includes(col.name);
                const isAutoExcluded =
                  ["id_like", "constant", "text"].includes(col.inferred_type) ||
                  col.missing_pct > 0.5;

                return (
                  <div
                    key={col.name}
                    onClick={() => {
                      if (isSelected) {
                        setSelectedFeatures((prev) => prev.filter((f) => f !== col.name));
                      } else {
                        setSelectedFeatures((prev) => [...prev, col.name]);
                      }
                    }}
                    className={`p-3 rounded-xl border cursor-pointer transition-all ${
                      isSelected
                        ? "border-cyan-500 bg-cyan-950/20"
                        : isAutoExcluded
                        ? "border-slate-800/50 bg-slate-900/30 opacity-70"
                        : "border-slate-800 bg-slate-900/60 hover:border-slate-700"
                    }`}
                  >
                    <div className="flex items-center justify-between">
                      <div className="flex items-center gap-2">
                        <div
                          className={`w-4 h-4 rounded border flex items-center justify-center ${
                            isSelected
                              ? "bg-cyan-500 border-cyan-400 text-black"
                              : "border-slate-700 bg-slate-800"
                          }`}
                        >
                          {isSelected && <Check className="w-3 h-3 stroke-[3]" />}
                        </div>
                        <span className="text-xs font-mono font-medium text-slate-200 truncate max-w-[150px]">
                          {col.name}
                        </span>
                      </div>
                      <span className="text-[10px] uppercase font-mono px-1 rounded bg-slate-800 text-slate-400">
                        {col.inferred_type}
                      </span>
                    </div>

                    {isAutoExcluded && (
                      <div className="mt-2 text-[10px] text-amber-400/90 font-mono">
                        Auto-excluded ({col.inferred_type})
                      </div>
                    )}
                  </div>
                );
              })}
          </div>

          <div className="text-xs text-slate-400 font-mono pt-2">
            Selected: {selectedFeatures.length} feature columns
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 4: MODEL SELECTION */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 4 && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white">Select Algorithm</h2>
            <p className="text-sm text-slate-400 mt-1">
              Choose an ML model tailored for {taskType} tasks.
            </p>
          </div>

          {loadingModels ? (
            <div className="p-8 text-center text-slate-400">Loading algorithms...</div>
          ) : (
            <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
              {models
                .filter((m) => m.task.includes(taskType))
                .map((m) => {
                  const isSelected = selectedModelId === m.id;
                  const isRecommended =
                    m.recommended ||
                    m.id === "random_forest" ||
                    m.id === "xgboost";

                  return (
                    <div
                      key={m.id}
                      onClick={() => {
                        setSelectedModelId(m.id);
                        initDefaultsForModel(m);
                      }}
                      className={`p-5 rounded-xl border cursor-pointer relative transition-all ${
                        isSelected
                          ? "border-cyan-500 bg-cyan-950/30 shadow-md shadow-cyan-500/15"
                          : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
                      }`}
                    >
                      <div className="flex items-start justify-between">
                        <div>
                          <div className="flex items-center gap-2">
                            <h4 className="font-semibold text-white">{m.name}</h4>
                            {isRecommended && (
                              <span className="px-2 py-0.5 rounded-full text-[10px] font-semibold bg-emerald-950/70 border border-emerald-800/80 text-emerald-300">
                                Recommended
                              </span>
                            )}
                          </div>
                          <p className="text-xs text-slate-400 mt-1.5 leading-relaxed">
                            {m.description}
                          </p>
                        </div>
                        <div
                          className={`w-5 h-5 rounded-full border flex items-center justify-center flex-shrink-0 ${
                            isSelected
                              ? "border-cyan-400 bg-cyan-500 text-black"
                              : "border-slate-700"
                          }`}
                        >
                          {isSelected && <Check className="w-3.5 h-3.5" />}
                        </div>
                      </div>

                      <div className="mt-4 pt-3 border-t border-slate-800/80 flex items-center gap-2 text-[11px] text-slate-500 font-mono">
                        <span>{m.needs_scaling ? "Auto-scales features" : "Tree-based (scale-invariant)"}</span>
                      </div>
                    </div>
                  );
                })}
            </div>
          )}
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 5: HYPERPARAMETERS & PREPROCESSING */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 5 && selectedModel && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div className="flex items-center justify-between">
            <div>
              <h2 className="text-xl font-bold text-white">
                Hyperparameters: {selectedModel.name}
              </h2>
              <p className="text-sm text-slate-400 mt-1">
                Tune parameters or stick with optimal defaults verified on benchmarks.
              </p>
            </div>
            <button
              type="button"
              onClick={() => initDefaultsForModel(selectedModel)}
              className="text-xs px-3 py-1.5 rounded-lg bg-slate-800 hover:bg-slate-700 text-slate-300 flex items-center gap-1.5"
            >
              <RotateCcw className="w-3 h-3" />
              Reset to Defaults
            </button>
          </div>

          {/* Dynamic Hyperparameters Form */}
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5 p-5 rounded-xl bg-slate-900/60 border border-slate-800">
            {Object.entries(selectedModel.hyperparameters).map(([key, def]) => {
              const val = hyperparameters[key] ?? def.default;

              return (
                <div key={key} className="space-y-1.5">
                  <div className="flex items-center justify-between">
                    <label className="text-xs font-semibold text-slate-200 font-mono">
                      {key}
                    </label>
                    <span className="text-[11px] text-slate-400 font-mono">
                      {String(val)}
                    </span>
                  </div>

                  {def.type === "int" || def.type === "float" ? (
                    <div className="flex items-center gap-3">
                      <input
                        type="range"
                        min={def.min ?? 1}
                        max={def.max ?? 100}
                        step={def.step ?? (def.type === "float" ? 0.01 : 1)}
                        value={val ?? def.default}
                        onChange={(e) =>
                          setHyperparameters({
                            ...hyperparameters,
                            [key]:
                              def.type === "float"
                                ? parseFloat(e.target.value)
                                : parseInt(e.target.value, 10),
                          })
                        }
                        className="flex-1 accent-cyan-500"
                      />
                      <input
                        type="number"
                        min={def.min}
                        max={def.max}
                        step={def.step}
                        value={val ?? ""}
                        onChange={(e) =>
                          setHyperparameters({
                            ...hyperparameters,
                            [key]:
                              e.target.value === ""
                                ? null
                                : def.type === "float"
                                ? parseFloat(e.target.value)
                                : parseInt(e.target.value, 10),
                          })
                        }
                        className="w-20 px-2 py-1 rounded bg-slate-800 border border-slate-700 text-xs text-white font-mono"
                      />
                    </div>
                  ) : def.options ? (
                    <select
                      value={val ?? ""}
                      onChange={(e) =>
                        setHyperparameters({
                          ...hyperparameters,
                          [key]: e.target.value,
                        })
                      }
                      className="w-full px-3 py-1.5 rounded-lg bg-slate-800 border border-slate-700 text-white text-xs"
                    >
                      {def.options.map((opt) => (
                        <option key={opt} value={opt}>
                          {opt}
                        </option>
                      ))}
                    </select>
                  ) : def.type === "bool" ? (
                    <div className="flex items-center gap-2">
                      <input
                        type="checkbox"
                        checked={!!val}
                        onChange={(e) =>
                          setHyperparameters({
                            ...hyperparameters,
                            [key]: e.target.checked,
                          })
                        }
                        className="w-4 h-4 rounded accent-cyan-500"
                      />
                      <span className="text-xs text-slate-300">Enabled</span>
                    </div>
                  ) : null}

                  <p className="text-[11px] text-slate-400">{def.description}</p>
                </div>
              );
            })}
          </div>

          {/* Collapsible Advanced Preprocessing Section */}
          <div className="border border-slate-800 rounded-xl overflow-hidden">
            <button
              type="button"
              onClick={() => setShowAdvanced(!showAdvanced)}
              className="w-full p-4 bg-slate-900/80 flex items-center justify-between text-xs font-semibold text-slate-300 hover:text-white"
            >
              <span>Advanced: Data Preprocessing, Splits & Cross Validation</span>
              {showAdvanced ? (
                <ChevronUp className="w-4 h-4" />
              ) : (
                <ChevronDown className="w-4 h-4" />
              )}
            </button>

            {showAdvanced && (
              <div className="p-5 bg-slate-950/40 grid grid-cols-1 sm:grid-cols-2 gap-4 text-xs">
                <div>
                  <label className="block text-slate-300 mb-1">
                    Hold-out Test Split Size ({(testSize * 100).toFixed(0)}%)
                  </label>
                  <input
                    type="range"
                    min={0.1}
                    max={0.4}
                    step={0.05}
                    value={testSize}
                    onChange={(e) => setTestSize(parseFloat(e.target.value))}
                    className="w-full accent-cyan-500"
                  />
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">
                    K-Fold Cross-Validation ({cvFolds === 0 ? "Off" : `${cvFolds} Folds`})
                  </label>
                  <select
                    value={cvFolds}
                    onChange={(e) => setCvFolds(parseInt(e.target.value, 10))}
                    className="w-full px-3 py-1.5 rounded bg-slate-800 border border-slate-700 text-white"
                  >
                    <option value={0}>Disabled (Train/Test only)</option>
                    <option value={3}>3-Fold CV</option>
                    <option value={5}>5-Fold CV (Recommended)</option>
                    <option value={10}>10-Fold CV</option>
                  </select>
                </div>
                <div>
                  <label className="block text-slate-300 mb-1">Numeric Imputation</label>
                  <select
                    value={numericImpute}
                    onChange={(e) =>
                      setNumericImpute(e.target.value as "mean" | "median")
                    }
                    className="w-full px-3 py-1.5 rounded bg-slate-800 border border-slate-700 text-white"
                  >
                    <option value="mean">Mean Strategy</option>
                    <option value="median">Median Strategy</option>
                  </select>
                </div>
                <div className="flex flex-col sm:flex-row sm:items-center gap-3 pt-4">
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={scaleNumeric}
                      onChange={(e) => setScaleNumeric(e.target.checked)}
                      className="accent-cyan-500 w-4 h-4"
                    />
                    <span className="text-slate-300">StandardScaler on numerics</span>
                  </label>
                  <label className="flex items-center gap-2 cursor-pointer">
                    <input
                      type="checkbox"
                      checked={dropIdLike}
                      onChange={(e) => setDropIdLike(e.target.checked)}
                      className="accent-cyan-500 w-4 h-4"
                    />
                    <span className="text-slate-300">Auto-drop ID-like columns</span>
                  </label>
                </div>
              </div>
            )}
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 6: COMPUTE SELECTION */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 6 && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white">Compute Infrastructure</h2>
            <p className="text-sm text-slate-400 mt-1">
              Select EC2 provisioning tier. Every training instance automatically self-terminates on completion.
            </p>
          </div>

          <div className="grid grid-cols-1 md:grid-cols-2 gap-4">
            {/* Small */}
            <div
              onClick={() => setComputeSize("small")}
              className={`p-5 rounded-xl border cursor-pointer transition-all ${
                computeSize === "small"
                  ? "border-cyan-500 bg-cyan-950/30 shadow-md shadow-cyan-500/15"
                  : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="font-semibold text-white">Small Tier</h4>
                    <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-emerald-950/80 text-emerald-400 border border-emerald-800/80">
                      Free Tier Eligible
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 mt-2 font-mono">
                    2 vCPUs • 4 GiB RAM • t3.small / t4g.small
                  </p>
                  <p className="text-xs text-slate-300 mt-2">
                    Ideal for small-to-medium tabular datasets (&lt; 20 MB). Quick startup and zero wasted resources.
                  </p>
                </div>
                <div
                  className={`w-5 h-5 rounded-full border flex items-center justify-center flex-shrink-0 ${
                    computeSize === "small"
                      ? "border-cyan-400 bg-cyan-500 text-black"
                      : "border-slate-700"
                  }`}
                >
                  {computeSize === "small" && <Check className="w-3.5 h-3.5" />}
                </div>
              </div>
            </div>

            {/* Medium */}
            <div
              onClick={() => setComputeSize("medium")}
              className={`p-5 rounded-xl border cursor-pointer transition-all ${
                computeSize === "medium"
                  ? "border-cyan-500 bg-cyan-950/30 shadow-md shadow-cyan-500/15"
                  : "border-slate-800 bg-slate-900/50 hover:border-slate-700"
              }`}
            >
              <div className="flex items-start justify-between">
                <div>
                  <div className="flex items-center gap-2">
                    <h4 className="font-semibold text-white">Medium Tier</h4>
                    {selectedDataset && selectedDataset.size_bytes > 20 * 1024 * 1024 && (
                      <span className="text-[10px] uppercase font-mono px-2 py-0.5 rounded bg-cyan-950/80 text-cyan-400 border border-cyan-800/80">
                        Recommended
                      </span>
                    )}
                  </div>
                  <p className="text-xs text-slate-400 mt-2 font-mono">
                    4 vCPUs • 8 GiB RAM • t3.medium / t4g.medium
                  </p>
                  <p className="text-xs text-slate-300 mt-2">
                    Faster multi-core training for larger datasets (&gt; 20 MB) or compute-heavy ensembles like XGBoost.
                  </p>
                </div>
                <div
                  className={`w-5 h-5 rounded-full border flex items-center justify-center flex-shrink-0 ${
                    computeSize === "medium"
                      ? "border-cyan-400 bg-cyan-500 text-black"
                      : "border-slate-700"
                  }`}
                >
                  {computeSize === "medium" && <Check className="w-3.5 h-3.5" />}
                </div>
              </div>
            </div>
          </div>
        </div>
      )}

      {/* ────────────────────────────────────────────────────────── */}
      {/* STEP 7: REVIEW & TRAIN */}
      {/* ────────────────────────────────────────────────────────── */}
      {currentStep === 7 && (
        <div className="p-6 rounded-2xl glass-panel space-y-6">
          <div>
            <h2 className="text-xl font-bold text-white">Review & Launch Training</h2>
            <p className="text-sm text-slate-400 mt-1">
              Verify your pipeline configuration before submitting to the SQS jobs queue.
            </p>
          </div>

          {/* Job Name */}
          <div className="space-y-1.5 max-w-lg">
            <label className="block text-xs font-medium text-slate-300">
              Training Job Name
            </label>
            <input
              type="text"
              value={jobName}
              onChange={(e) => setJobName(e.target.value)}
              className="w-full px-4 py-2.5 rounded-xl bg-slate-900 border border-slate-700 text-white text-sm focus:outline-none focus:border-cyan-500 font-mono"
            />
          </div>

          {/* Configuration Summary Card */}
          <div className="grid grid-cols-1 sm:grid-cols-2 md:grid-cols-4 gap-4 p-5 rounded-xl bg-slate-900/60 border border-slate-800 text-xs">
            <div>
              <span className="text-slate-500 uppercase tracking-wider block">
                Dataset
              </span>
              <span className="font-semibold text-slate-200 mt-0.5 block truncate">
                {selectedDataset?.name}
              </span>
              <span className="text-[11px] font-mono text-slate-400">
                {selectedDataset?.profile?.row_count} rows
              </span>
            </div>

            <div>
              <span className="text-slate-500 uppercase tracking-wider block">
                Target & Task
              </span>
              <span className="font-semibold text-slate-200 mt-0.5 block font-mono">
                {targetColumn}
              </span>
              <span className="text-[11px] text-cyan-400 capitalize">
                {taskType}
              </span>
            </div>

            <div>
              <span className="text-slate-500 uppercase tracking-wider block">
                Algorithm
              </span>
              <span className="font-semibold text-slate-200 mt-0.5 block">
                {selectedModel?.name}
              </span>
              <span className="text-[11px] text-slate-400">
                {selectedFeatures.length} features
              </span>
            </div>

            <div>
              <span className="text-slate-500 uppercase tracking-wider block">
                Compute Tier
              </span>
              <span className="font-semibold text-slate-200 mt-0.5 block uppercase">
                {computeSize}
              </span>
              <span className="text-[11px] text-emerald-400 font-mono">
                Self-terminating
              </span>
            </div>
          </div>

          {/* Quota Notice */}
          <div className="p-4 rounded-xl bg-slate-900 border border-slate-800 flex items-center justify-between text-xs text-slate-400">
            <span>
              Active Capacity:{" "}
              <strong className="text-slate-200">
                {quotas?.active_jobs?.count ?? 0} of {quotas?.active_jobs?.max ?? 3}
              </strong>{" "}
              active training slots used
            </span>
            <span className="text-emerald-400 font-mono">Cost: $0.00 (Free Tier)</span>
          </div>
        </div>
      )}

      {/* Navigation Buttons */}
      <div className="flex items-center justify-between pt-4 border-t border-slate-800">
        <button
          type="button"
          onClick={prevStep}
          disabled={currentStep === 1 || isSubmitting}
          className={`flex items-center gap-2 px-4 py-2 rounded-xl text-sm font-medium transition-colors ${
            currentStep === 1
              ? "opacity-0 pointer-events-none"
              : "bg-slate-800 hover:bg-slate-700 text-slate-300"
          }`}
        >
          <ArrowLeft className="w-4 h-4" />
          Back
        </button>

        {currentStep < 7 ? (
          <button
            type="button"
            onClick={nextStep}
            className="flex items-center gap-2 px-6 py-2.5 rounded-xl bg-gradient-to-r from-cyan-500 to-blue-600 hover:from-cyan-400 hover:to-blue-500 text-white font-medium text-sm transition-all shadow-md shadow-cyan-500/20"
          >
            Next
            <ArrowRight className="w-4 h-4" />
          </button>
        ) : (
          <button
            type="button"
            onClick={handleLaunchTraining}
            disabled={isSubmitting}
            className="flex items-center gap-2 px-8 py-2.5 rounded-xl bg-gradient-to-r from-emerald-500 to-teal-600 hover:from-emerald-400 hover:to-teal-500 text-white font-medium text-sm transition-all shadow-lg shadow-emerald-500/25 disabled:opacity-50"
          >
            {isSubmitting ? (
              <>
                <div className="w-4 h-4 border-2 border-white border-t-transparent rounded-full animate-spin" />
                Dispatching to SQS...
              </>
            ) : (
              <>
                <Sparkles className="w-4 h-4" />
                Start Training Now
              </>
            )}
          </button>
        )}
      </div>
    </div>
  );
};
