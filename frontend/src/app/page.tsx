import { redirect } from 'next/navigation';

// `return` matters: redirect() is typed as returning never, and without it TS
// infers Home as () => void, which is not a valid JSX component type -- so the
// test that renders <Home /> fails to typecheck.
export default function Home() {
  return redirect('/draft');
}