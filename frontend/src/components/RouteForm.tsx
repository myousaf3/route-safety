import { useEffect, useId, useMemo, useState, type FormEvent } from "react";
import { useMutation, useQuery } from "@tanstack/react-query";
import { ApiError, createAnalysis, searchPlaces } from "../lib/api";
import {
  defaultDepartureInput,
  localTimezone,
  maxDepartureInput,
  toIsoWithOffset,
} from "../lib/format";
import type { Analysis, Place, Spacing } from "../types";

interface Props {
  onCreated: (analysis: Analysis) => void;
}

interface FormErrors {
  origin?: string;
  destination?: string;
  departure?: string;
  load_weight_lb?: string;
}

const LOAD_PRESETS = [10_000, 30_000, 42_000, 60_000, 80_000];

const STAGES = [
  "Geocoding origin and destination",
  "Requesting three route alternatives",
  "Sampling forecasts at checkpoint ETAs",
  "Scoring risk and ranking routes",
];

function useDebounced<T>(value: T, delay: number): T {
  const [debounced, setDebounced] = useState(value);
  useEffect(() => {
    const timer = window.setTimeout(() => setDebounced(value), delay);
    return () => window.clearTimeout(timer);
  }, [value, delay]);
  return debounced;
}

export default function RouteForm({ onCreated }: Props) {
  const formId = useId();
  const [origin, setOrigin] = useState("");
  const [destination, setDestination] = useState("");
  const [departure, setDeparture] = useState(defaultDepartureInput);
  const [weight, setWeight] = useState("42000");
  const [spacing, setSpacing] = useState<Spacing>(25);
  const [errors, setErrors] = useState<FormErrors>({});
  const [activeField, setActiveField] = useState<"origin" | "destination" | null>(null);
  const [stage, setStage] = useState(0);

  const browserTimezone = useMemo(localTimezone, []);

  const debouncedOrigin = useDebounced(origin, 400);
  const debouncedDestination = useDebounced(destination, 400);

  const originSearch = useQuery({
    queryKey: ["places", debouncedOrigin],
    queryFn: ({ signal }) => searchPlaces(debouncedOrigin, signal),
    enabled: activeField === "origin" && debouncedOrigin.trim().length >= 3,
    staleTime: 5 * 60_000,
  });

  const destinationSearch = useQuery({
    queryKey: ["places", debouncedDestination],
    queryFn: ({ signal }) => searchPlaces(debouncedDestination, signal),
    enabled: activeField === "destination" && debouncedDestination.trim().length >= 3,
    staleTime: 5 * 60_000,
  });

  const mutation = useMutation({
    mutationFn: createAnalysis,
    onSuccess: (analysis) => {
      onCreated(analysis);
    },
  });

  useEffect(() => {
    if (!mutation.isPending) {
      setStage(0);
      return;
    }
    const timer = window.setInterval(() => {
      setStage((current) => Math.min(current + 1, STAGES.length - 1));
    }, 2600);
    return () => window.clearInterval(timer);
  }, [mutation.isPending]);

  const validate = (): FormErrors => {
    const next: FormErrors = {};
    if (origin.trim().length < 3) next.origin = "Enter a city, address, or landmark.";
    if (destination.trim().length < 3) {
      next.destination = "Enter a city, address, or landmark.";
    }
    if (origin.trim().toLowerCase() === destination.trim().toLowerCase() && origin.trim()) {
      next.destination = "Origin and destination must be different.";
    }
    const parsedWeight = Number(weight);
    if (!Number.isFinite(parsedWeight) || parsedWeight < 1_000 || parsedWeight > 120_000) {
      next.load_weight_lb = "Load weight must be between 1,000 and 120,000 lb.";
    }
    const parsedDeparture = new Date(departure);
    if (Number.isNaN(parsedDeparture.getTime())) {
      next.departure = "Choose a valid departure date and time.";
    } else if (parsedDeparture.getTime() < Date.now() - 5 * 60_000) {
      next.departure = "Departure must be in the future.";
    } else if (parsedDeparture.getTime() > Date.now() + 15 * 24 * 60 * 60_000) {
      next.departure = "Forecasts are available up to 15 days ahead.";
    }
    return next;
  };

  const submit = (event: FormEvent<HTMLFormElement>) => {
    event.preventDefault();
    const validation = validate();
    setErrors(validation);
    if (Object.keys(validation).length > 0) return;
    mutation.mutate({
      origin: origin.trim(),
      destination: destination.trim(),
      departure: toIsoWithOffset(departure),
      load_weight_lb: Number(weight),
      spacing_miles: spacing,
    });
  };

  const serverError = mutation.error instanceof ApiError ? mutation.error : null;
  const suggestions: Place[] =
    activeField === "origin" ? originSearch.data ?? [] : destinationSearch.data ?? [];
  const searching =
    activeField === "origin" ? originSearch.isFetching : destinationSearch.isFetching;

  const pickPlace = (place: Place) => {
    if (activeField === "origin") setOrigin(place.label);
    if (activeField === "destination") setDestination(place.label);
    setActiveField(null);
  };

  return (
    <section className="panel form-panel" aria-labelledby={`${formId}-title`}>
      <div className="panel-heading">
        <div>
          <span className="eyebrow">New analysis</span>
          <h2 id={`${formId}-title`}>Plan a safer run</h2>
        </div>
      </div>

      <form onSubmit={submit} noValidate>
        {serverError && (
          <div className="inline-error" role="alert">
            <strong>{serverError.detail}</strong>
            {serverError.fieldErrors && (
              <ul>
                {Object.entries(serverError.fieldErrors).map(([field, message]) => (
                  <li key={field}>
                    {field.replaceAll("_", " ")}:{" "}
                    {Array.isArray(message) ? message.join(" ") : message}
                  </li>
                ))}
              </ul>
            )}
            {serverError.correlationId && (
              <span className="mono small">Ref: {serverError.correlationId.slice(0, 12)}</span>
            )}
          </div>
        )}

        <div className="field">
          <label htmlFor={`${formId}-origin`}>Origin</label>
          <div className="autocomplete">
            <input
              id={`${formId}-origin`}
              value={origin}
              onChange={(event) => {
                setOrigin(event.target.value);
                setActiveField("origin");
              }}
              onFocus={() => setActiveField("origin")}
              onBlur={() => window.setTimeout(() => setActiveField(null), 120)}
              placeholder="Chicago, IL"
              autoComplete="off"
              aria-invalid={Boolean(errors.origin)}
              aria-describedby={errors.origin ? `${formId}-origin-error` : undefined}
              aria-autocomplete="list"
              aria-expanded={activeField === "origin" && suggestions.length > 0}
            />
            {activeField === "origin" && (searching || suggestions.length > 0) && (
              <ul className="suggestions" role="listbox" aria-label="Origin suggestions">
                {searching && <li className="suggestion-status">Searching…</li>}
                {suggestions.map((place) => (
                  <li key={`${place.lat},${place.lon},${place.label}`}>
                    <button
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => pickPlace(place)}
                    >
                      <span>{place.label}</span>
                      <span className="suggestion-meta">{place.timezone}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {errors.origin && (
            <p className="field-error" id={`${formId}-origin-error`}>
              {errors.origin}
            </p>
          )}
        </div>

        <div className="field">
          <label htmlFor={`${formId}-destination`}>Destination</label>
          <div className="autocomplete">
            <input
              id={`${formId}-destination`}
              value={destination}
              onChange={(event) => {
                setDestination(event.target.value);
                setActiveField("destination");
              }}
              onFocus={() => setActiveField("destination")}
              onBlur={() => window.setTimeout(() => setActiveField(null), 120)}
              placeholder="Denver, CO"
              autoComplete="off"
              aria-invalid={Boolean(errors.destination)}
              aria-describedby={errors.destination ? `${formId}-destination-error` : undefined}
              aria-autocomplete="list"
              aria-expanded={activeField === "destination" && suggestions.length > 0}
            />
            {activeField === "destination" && (searching || suggestions.length > 0) && (
              <ul className="suggestions" role="listbox" aria-label="Destination suggestions">
                {searching && <li className="suggestion-status">Searching…</li>}
                {suggestions.map((place) => (
                  <li key={`${place.lat},${place.lon},${place.label}`}>
                    <button
                      type="button"
                      onMouseDown={(event) => event.preventDefault()}
                      onClick={() => pickPlace(place)}
                    >
                      <span>{place.label}</span>
                      <span className="suggestion-meta">{place.timezone}</span>
                    </button>
                  </li>
                ))}
              </ul>
            )}
          </div>
          {errors.destination && (
            <p className="field-error" id={`${formId}-destination-error`}>
              {errors.destination}
            </p>
          )}
        </div>

        <div className="field-row">
          <div className="field">
            <label htmlFor={`${formId}-departure`}>Departure</label>
            <input
              id={`${formId}-departure`}
              type="datetime-local"
              value={departure}
              max={maxDepartureInput()}
              onChange={(event) => setDeparture(event.target.value)}
              aria-invalid={Boolean(errors.departure)}
              aria-describedby={`${formId}-departure-help`}
            />
            <p className="field-help" id={`${formId}-departure-help`}>
              {browserTimezone} · converted to UTC for forecast lookup
            </p>
            {errors.departure && <p className="field-error">{errors.departure}</p>}
          </div>

          <div className="field">
            <label htmlFor={`${formId}-weight`}>Load weight (lb)</label>
            <input
              id={`${formId}-weight`}
              type="number"
              inputMode="numeric"
              min={1000}
              max={120000}
              step={500}
              value={weight}
              onChange={(event) => setWeight(event.target.value)}
              aria-invalid={Boolean(errors.load_weight_lb)}
            />
            <p className="field-help">1,000 – 120,000 lb</p>
            {errors.load_weight_lb && <p className="field-error">{errors.load_weight_lb}</p>}
          </div>
        </div>

        <div className="weight-presets" aria-label="Load weight presets">
          {LOAD_PRESETS.map((preset) => (
            <button
              key={preset}
              type="button"
              className={Number(weight) === preset ? "chip chip-active" : "chip"}
              onClick={() => setWeight(String(preset))}
            >
              {preset.toLocaleString()} lb
            </button>
          ))}
        </div>

        <fieldset className="field spacing-field">
          <legend>Checkpoint detail</legend>
          <div className="segmented">
            {([10, 25, 50] as Spacing[]).map((option) => (
              <label key={option} className={spacing === option ? "segment active" : "segment"}>
                <input
                  type="radio"
                  name="spacing"
                  value={option}
                  checked={spacing === option}
                  onChange={() => setSpacing(option)}
                />
                {option} mi
              </label>
            ))}
          </div>
          <p className="field-help">
            Detail view only — risk totals are always distance-weighted from 10-mile samples.
          </p>
        </fieldset>

        <button type="submit" className="btn btn-primary" disabled={mutation.isPending}>
          {mutation.isPending ? (
            <>
              <span className="spinner spinner-small" aria-hidden="true" /> Analyzing…
            </>
          ) : (
            "Find the safest route"
          )}
        </button>

        <div className="form-status" aria-live="polite">
          {mutation.isPending && (
            <div className="analysis-progress">
              <div className="progress-track">
                <div
                  className="progress-fill"
                  style={{ width: `${((stage + 1) / STAGES.length) * 100}%` }}
                />
              </div>
              <span>{STAGES[stage]}</span>
            </div>
          )}
        </div>
      </form>
    </section>
  );
}
