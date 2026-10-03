const BORO: Record<string, string> = { '1': 'Manhattan', '2': 'Bronx', '3': 'Brooklyn', '4': 'Queens', '5': 'Staten Island' }

/** 401 -> "Queens 1" (DCP borough code + district number). */
export function districtName(code: string): string {
  return `${BORO[code[0]] ?? code[0]} ${Number(code.slice(1))}`
}
