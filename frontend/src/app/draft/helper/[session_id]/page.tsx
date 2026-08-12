import DraftRoom from '../../_components/DraftRoom';

/*
  Same room, live opponents. The picks arrive from Sleeper rather than from a
  button, so this mode polls and never offers to simulate -- the backend rejects
  a CPU pick for any session carrying a draft_id.
*/
export default function LiveDraftPage() {
  return <DraftRoom mode="live" />;
}
