import type { ResultPayload } from "../types";
import { TrialView } from "./TrialView";

export function ResultView({ result, onReplay }: { result: ResultPayload; onReplay?: () => void }) {
  return <TrialView result={result} onReplay={onReplay} />;
}
