import { signOutAction } from "@/auth/actions";
import { currentSession } from "@/auth/session";
import { SessionMenu } from "@/components/SessionMenu";

/** Who is signed in, always as a demo identity, with a persona dropdown menu. */
export async function SessionBar() {
  const session = await currentSession();
  return <SessionMenu session={session} signOutAction={signOutAction} />;
}
