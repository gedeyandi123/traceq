export type RoleFlags = {
  mayDecide: boolean;
  mayApprove: boolean;
  mayExecute: boolean;
  mayWitness: boolean;
};

export type RoleKey = "canDecide" | "canApprove" | "canExecute" | "canWitness" | "readOnly";

export function initials(name: string): string {
  return name
    .split(/\s+/)
    .slice(0, 2)
    .map((w) => w.charAt(0))
    .join("")
    .toUpperCase();
}

export function resolveRoleKey(flags: RoleFlags): RoleKey {
  if (flags.mayDecide) return "canDecide";
  if (flags.mayApprove) return "canApprove";
  if (flags.mayExecute) return "canExecute";
  if (flags.mayWitness) return "canWitness";
  return "readOnly";
}

export function resolveRoleSummary(
  flags: RoleFlags,
  t: (key: RoleKey) => string,
): string {
  const active: string[] = [];
  if (flags.mayDecide) active.push(t("canDecide"));
  if (flags.mayApprove) active.push(t("canApprove"));
  if (flags.mayExecute) active.push(t("canExecute"));
  if (flags.mayWitness) active.push(t("canWitness"));
  return active.length > 0 ? active.join(" · ") : t("readOnly");
}
