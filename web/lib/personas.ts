/** Demo members (synthetic). The backend signs a session per persona through /v1/auth/dev-login. */
export const PERSONAS = [
  { id: "U1001", name: "Ananya Rao", place: "Bangalore", note: "Parent of Aarav · cares for father Venkat" },
  { id: "U1002", name: "Rahul Mehta", place: "Mumbai", note: "Cataract surgery journey · own records only" },
  { id: "U1003", name: "Fatima Shaikh", place: "Hyderabad", note: "Parent of Zoya · mother's consent expired" },
] as const;

export const persona = (id: string) => PERSONAS.find((p) => p.id === id) ?? PERSONAS[0];
