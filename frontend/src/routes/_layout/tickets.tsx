import { zodResolver } from "@hookform/resolvers/zod"
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query"
import { createFileRoute } from "@tanstack/react-router"
import {
  AlertTriangle,
  CheckCircle,
  Clock,
  Loader2,
  Plus,
  TicketIcon,
  Trash2,
  UserCheck,
} from "lucide-react"
import type React from "react"
import { useEffect, useState } from "react"
import { useForm } from "react-hook-form"
import { z } from "zod"

import { type TicketCreate, type TicketPublic, TicketsService } from "@/client"
import { Badge } from "@/components/ui/badge"
import { Button } from "@/components/ui/button"
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card"
import {
  Dialog,
  DialogClose,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
  DialogTrigger,
} from "@/components/ui/dialog"
import {
  Form,
  FormControl,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form"
import { Input } from "@/components/ui/input"
import { LoadingButton } from "@/components/ui/loading-button"
import { Textarea } from "@/components/ui/textarea"
import useCustomToast from "@/hooks/useCustomToast"
import { handleError } from "@/utils"

// ─── Route ───────────────────────────────────────────────────────────────────

export const Route = createFileRoute("/_layout/tickets")({
  component: TicketsPage,
  head: () => ({
    meta: [{ title: "Support Tickets" }],
  }),
})

// ─── Helpers ─────────────────────────────────────────────────────────────────

type StatusConfigEntry = {
  label: string
  icon: React.ComponentType<{ className?: string }>
  variant: "secondary" | "outline" | "default" | "destructive"
  spin?: boolean
}

const statusConfig: Record<string, StatusConfigEntry> = {
  open: { label: "Open", icon: Clock, variant: "secondary" },
  analyzing: {
    label: "Analyzing…",
    icon: Loader2,
    variant: "outline",
    spin: true,
  },
  resolved: { label: "Resolved", icon: CheckCircle, variant: "default" },
  escalated: { label: "Needs Review", icon: UserCheck, variant: "destructive" },
}

const priorityColors = {
  low: "bg-blue-500/10 text-blue-600 border-blue-200",
  medium: "bg-yellow-500/10 text-yellow-600 border-yellow-200",
  high: "bg-orange-500/10 text-orange-600 border-orange-200",
  critical: "bg-red-500/10 text-red-600 border-red-200",
}

function StatusBadge({ status }: { status: string }) {
  const config =
    statusConfig[status as keyof typeof statusConfig] ?? statusConfig.open
  const Icon = config.icon
  return (
    <Badge variant={config.variant} className="flex items-center gap-1">
      <Icon className={`h-3 w-3 ${config.spin ? "animate-spin" : ""}`} />
      {config.label}
    </Badge>
  )
}

function ConfidenceBar({ value }: { value: number }) {
  const pct = Math.round(value * 100)
  const color =
    pct >= 80 ? "bg-green-500" : pct >= 50 ? "bg-yellow-500" : "bg-red-500"
  return (
    <div className="flex items-center gap-2">
      <div className="flex-1 h-1.5 rounded-full bg-muted overflow-hidden">
        <div
          className={`h-full ${color} rounded-full`}
          style={{ width: `${pct}%` }}
        />
      </div>
      <span className="text-xs text-muted-foreground w-8 text-right">
        {pct}%
      </span>
    </div>
  )
}

// ─── Submit Ticket Dialog ─────────────────────────────────────────────────────

const formSchema = z.object({
  title: z.string().min(1, "Title is required").max(255),
  description: z.string().min(1, "Description is required").max(5000),
})
type FormData = z.infer<typeof formSchema>

function SubmitTicketDialog() {
  const [open, setOpen] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  const form = useForm<FormData>({
    resolver: zodResolver(formSchema),
    defaultValues: { title: "", description: "" },
  })

  const mutation = useMutation({
    mutationFn: (data: TicketCreate) =>
      TicketsService.createTicket({ requestBody: data }),
    onSuccess: () => {
      showSuccessToast("Ticket submitted — Claude is analyzing it now")
      form.reset()
      setOpen(false)
      queryClient.invalidateQueries({ queryKey: ["tickets"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  return (
    <Dialog open={open} onOpenChange={setOpen}>
      <DialogTrigger asChild>
        <Button>
          <Plus className="mr-2 h-4 w-4" />
          Submit Ticket
        </Button>
      </DialogTrigger>
      <DialogContent className="sm:max-w-lg">
        <DialogHeader>
          <DialogTitle>Submit Support Ticket</DialogTitle>
          <DialogDescription>
            Describe your issue. Claude will analyze it and provide a diagnosis.
          </DialogDescription>
        </DialogHeader>
        <Form {...form}>
          <form onSubmit={form.handleSubmit((d) => mutation.mutate(d))}>
            <div className="grid gap-4 py-4">
              <FormField
                control={form.control}
                name="title"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Title <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Input
                        placeholder="e.g. Login failing with 403 error"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
              <FormField
                control={form.control}
                name="description"
                render={({ field }) => (
                  <FormItem>
                    <FormLabel>
                      Description <span className="text-destructive">*</span>
                    </FormLabel>
                    <FormControl>
                      <Textarea
                        placeholder="Describe what you're experiencing, steps to reproduce, and any error messages…"
                        className="min-h-[120px]"
                        {...field}
                      />
                    </FormControl>
                    <FormMessage />
                  </FormItem>
                )}
              />
            </div>
            <DialogFooter>
              <DialogClose asChild>
                <Button variant="outline" disabled={mutation.isPending}>
                  Cancel
                </Button>
              </DialogClose>
              <LoadingButton type="submit" loading={mutation.isPending}>
                Submit
              </LoadingButton>
            </DialogFooter>
          </form>
        </Form>
      </DialogContent>
    </Dialog>
  )
}

// ─── Ticket Card ─────────────────────────────────────────────────────────────

function TicketCard({ ticket }: { ticket: TicketPublic }) {
  const [expanded, setExpanded] = useState(false)
  const queryClient = useQueryClient()
  const { showSuccessToast, showErrorToast } = useCustomToast()

  // Poll while analyzing
  const { data: polled } = useQuery({
    queryKey: ["ticket", ticket.id],
    queryFn: () => TicketsService.readTicket({ id: ticket.id }),
    refetchInterval: ticket.status === "analyzing" ? 3000 : false,
    enabled: ticket.status === "analyzing",
  })

  useEffect(() => {
    if (polled && polled.status !== "analyzing") {
      queryClient.invalidateQueries({ queryKey: ["tickets"] })
    }
  }, [polled?.status, queryClient, polled])

  const deleteMutation = useMutation({
    mutationFn: () => TicketsService.deleteTicket({ id: ticket.id }),
    onSuccess: () => {
      showSuccessToast("Ticket deleted")
      queryClient.invalidateQueries({ queryKey: ["tickets"] })
    },
    onError: handleError.bind(showErrorToast),
  })

  const analysis = ticket.analysis

  return (
    <Card className="transition-shadow hover:shadow-md">
      <CardHeader className="pb-3">
        <div className="flex items-start justify-between gap-3">
          <div className="flex-1 min-w-0">
            <CardTitle className="text-base leading-snug truncate">
              {ticket.title}
            </CardTitle>
            <CardDescription className="mt-1 text-xs">
              {new Date(ticket.created_at ?? "").toLocaleDateString("en-US", {
                month: "short",
                day: "numeric",
                hour: "2-digit",
                minute: "2-digit",
              })}
            </CardDescription>
          </div>
          <div className="flex items-center gap-2 shrink-0">
            {analysis?.priority && (
              <span
                className={`text-xs font-medium px-2 py-0.5 rounded-full border ${
                  priorityColors[
                    analysis.priority as keyof typeof priorityColors
                  ]
                }`}
              >
                {analysis.priority}
              </span>
            )}
            <StatusBadge status={ticket.status} />
            <Button
              variant="ghost"
              size="icon"
              className="h-7 w-7 text-muted-foreground hover:text-destructive"
              onClick={() => deleteMutation.mutate()}
              disabled={deleteMutation.isPending}
            >
              <Trash2 className="h-3.5 w-3.5" />
            </Button>
          </div>
        </div>
      </CardHeader>

      <CardContent className="pt-0 space-y-3">
        <p className="text-sm text-muted-foreground line-clamp-2">
          {ticket.description}
        </p>

        {analysis && (
          <>
            <div className="rounded-lg border bg-muted/40 p-3 space-y-2">
              <div className="flex items-center justify-between">
                <span className="text-xs font-semibold uppercase tracking-wide text-muted-foreground">
                  AI Analysis
                </span>
                <div className="flex items-center gap-2">
                  <span className="text-xs text-muted-foreground">
                    Confidence
                  </span>
                  <div className="w-24">
                    <ConfidenceBar value={analysis.confidence} />
                  </div>
                </div>
              </div>
              <p className="text-sm font-medium">{analysis.summary}</p>

              {expanded && (
                <div className="space-y-2 pt-1">
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-0.5">
                      Diagnosis
                    </p>
                    <p className="text-sm">{analysis.diagnosis}</p>
                  </div>
                  <div>
                    <p className="text-xs font-semibold text-muted-foreground mb-0.5">
                      Suggested Fix
                    </p>
                    <p className="text-sm">{analysis.suggested_fix}</p>
                  </div>
                  {analysis.needs_human && (
                    <div className="flex items-center gap-1.5 text-xs text-orange-600 bg-orange-50 dark:bg-orange-950/30 rounded px-2 py-1">
                      <AlertTriangle className="h-3.5 w-3.5" />
                      Flagged for human engineer review
                    </div>
                  )}
                </div>
              )}
            </div>

            <Button
              variant="ghost"
              size="sm"
              className="h-7 text-xs text-muted-foreground -ml-1"
              onClick={() => setExpanded(!expanded)}
            >
              {expanded ? "Show less" : "Show full analysis"}
            </Button>
          </>
        )}

        {ticket.status === "analyzing" && !analysis && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground py-1">
            <Loader2 className="h-4 w-4 animate-spin" />
            Claude is analyzing this ticket…
          </div>
        )}
      </CardContent>
    </Card>
  )
}

// ─── Page ─────────────────────────────────────────────────────────────────────

function TicketsPage() {
  const { data, isLoading } = useQuery({
    queryKey: ["tickets"],
    queryFn: () => TicketsService.readTickets({ skip: 0, limit: 100 }),
    refetchInterval: 5000, // refresh list every 5s to catch status updates
  })

  const tickets = data?.data ?? []

  return (
    <div className="flex flex-col gap-6">
      <div className="flex items-center justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight">Support Tickets</h1>
          <p className="text-muted-foreground">
            Submit issues and let Claude diagnose them automatically
          </p>
        </div>
        <SubmitTicketDialog />
      </div>

      {isLoading ? (
        <div className="flex items-center justify-center py-16 text-muted-foreground">
          <Loader2 className="h-6 w-6 animate-spin mr-2" />
          Loading tickets…
        </div>
      ) : tickets.length === 0 ? (
        <div className="flex flex-col items-center justify-center text-center py-16 gap-3">
          <div className="rounded-full bg-muted p-4">
            <TicketIcon className="h-8 w-8 text-muted-foreground" />
          </div>
          <h3 className="text-lg font-semibold">No tickets yet</h3>
          <p className="text-muted-foreground text-sm">
            Submit your first ticket to see Claude in action
          </p>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {tickets.map((ticket) => (
            <TicketCard key={ticket.id} ticket={ticket} />
          ))}
        </div>
      )}
    </div>
  )
}
