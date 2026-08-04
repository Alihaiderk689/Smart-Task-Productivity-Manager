// Shared by login.jsx (after a successful sign-in) and PublicOnlyRoute (an
// already-authenticated user landing on /login or /register) so both paths
// send the user to the same place. Only ever redirects to a same-app path,
// never an external URL.
//
// Staff accounts always land on /admin -- RoleRoute would bounce them there
// anyway if "from" pointed at a regular page, so decide it up front instead
// of letting them flash the wrong page first.
export function getAuthedRedirectDestination(location, isStaff) {
  if (isStaff) {
    return "/admin";
  }

  const stateFrom = location.state?.from;
  if (typeof stateFrom === "string" && stateFrom.startsWith("/")) {
    return stateFrom;
  }

  const queryFrom = new URLSearchParams(location.search).get("from");
  if (queryFrom && queryFrom.startsWith("/")) {
    return queryFrom;
  }

  return "/";
}
