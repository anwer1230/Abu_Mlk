import { format } from "date-fns";

export function formatDateTime(dateString: string) {
  return format(new Date(dateString), "MMM d, yyyy 'at' h:mm a");
}

export function formatDateShort(dateString: string) {
  return format(new Date(dateString), "MMM d, yyyy");
}
