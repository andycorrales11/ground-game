import DraftRoom from '../../_components/DraftRoom';

/*
  The room itself is mode-agnostic. What makes this the simulation is that its
  CPU opponents have to be advanced by hand and there is nothing to poll --
  both encoded in DraftRoom's MODES table, not here.
*/
export default function SimulationDraftPage() {
  return <DraftRoom mode="simulation" />;
}
