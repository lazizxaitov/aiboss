export type ClassValue = string | number | false | null | undefined;

export function cn(...values: ClassValue[]) {
  return values.filter((value): value is string | number => value !== false && value != null).join(" ");
}
