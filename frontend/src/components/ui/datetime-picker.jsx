import { useRef, useState } from "react";
import { format, isValid, parse } from "date-fns";
import { CalendarIcon, Clock } from "lucide-react";
import { Popover, PopoverContent, PopoverTrigger } from "@/components/ui/popover";
import { Calendar } from "@/components/ui/calendar";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { cn } from "@/lib/utils";

const LOCAL_FORMAT = "yyyy-MM-dd'T'HH:mm";

// value/onChange use the same "yyyy-MM-ddTHH:mm" local-time string the rest
// of the app already stores form state as -- swap-in replacement for
// <input type="datetime-local">, just with a real calendar + time picker
// instead of typed digit segments.
export default function DateTimePicker({ id = undefined, value, onChange, placeholder = "Pick a date & time", required = false, minDate = undefined }) {
  const [open, setOpen] = useState(false);
  const triggerRef = useRef(null);

  const handleOpenChange = (nextOpen) => {
    if (nextOpen) {
      // Fields near the bottom of a tall dialog leave little room below for
      // the calendar, forcing it to flip above the trigger and cover the
      // dialog's own header/other fields. Centering the trigger first gives
      // the popover room on both sides, so it only needs to flip when the
      // viewport is genuinely too short for it either way.
      triggerRef.current?.scrollIntoView({ behavior: "smooth", block: "center" });
    }
    setOpen(nextOpen);
  };

  const parsedDate = value ? parse(value, LOCAL_FORMAT, new Date()) : null;
  const selectedDate = parsedDate && isValid(parsedDate) ? parsedDate : null;
  const timeValue = selectedDate ? format(selectedDate, "HH:mm") : "";

  const commit = (date, time) => {
    if (!date) return;
    const [hours, minutes] = (time || "09:00").split(":").map(Number);
    const combined = new Date(date);
    combined.setHours(hours, minutes, 0, 0);
    onChange(format(combined, LOCAL_FORMAT));
  };

  return (
    <Popover open={open} onOpenChange={handleOpenChange}>
      <PopoverTrigger asChild>
        <button
          ref={triggerRef}
          type="button"
          id={id}
          className={cn(
            "flex h-10 w-full items-center gap-2 rounded-md border border-input bg-background px-3 py-2 text-sm ring-offset-background",
            "hover:bg-accent/50 transition-colors focus-visible:outline-none focus-visible:ring-2 focus-visible:ring-ring focus-visible:ring-offset-2",
            !selectedDate && "text-muted-foreground"
          )}
        >
          <CalendarIcon className="h-4 w-4 shrink-0 opacity-60" aria-hidden="true" />
          <span className="flex-1 text-left truncate">
            {selectedDate ? format(selectedDate, "d MMM yyyy, h:mm a") : placeholder}
          </span>
        </button>
      </PopoverTrigger>
      <PopoverContent className="w-auto p-0" align="start" collisionPadding={16}>
        <Calendar
          mode="single"
          selected={selectedDate || undefined}
          onSelect={(date) => commit(date, timeValue || "09:00")}
          disabled={minDate ? { before: minDate } : undefined}
          initialFocus
        />
        <div className="flex items-center gap-2 border-t border-border p-3">
          <Clock className="h-4 w-4 shrink-0 opacity-60" aria-hidden="true" />
          <Input
            type="time"
            value={timeValue}
            onChange={(e) => commit(selectedDate || new Date(), e.target.value)}
            className="h-9"
            required={required}
          />
          <Button type="button" size="sm" onClick={() => setOpen(false)} disabled={!selectedDate}>
            Done
          </Button>
        </div>
      </PopoverContent>
    </Popover>
  );
}
