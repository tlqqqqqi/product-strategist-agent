// Append each message the user sends to cases/.inbox.jsonl (read by bin/strat: a gate approval
// must follow the user's yes, see strat/inbox.py). Never throws into the session.
import { appendFileSync, mkdirSync } from "node:fs"
import { join } from "node:path"

export const StratInbox = async ({ directory }) => {
  const cases = process.env.STRAT_CASES || join(directory, "cases")
  return {
    "chat.message": async (_input, output) => {
      try {
        const parts = (output && output.parts) || []
        const text = parts
          .filter((p) => p && p.type === "text" && !p.synthetic && typeof p.text === "string")
          .map((p) => p.text)
          .join("\n")
          .trim()
          .replace(/^"([\s\S]*)"$/, "$1") // `opencode run "<msg>"` keeps the quotes
        if (!text) return
        mkdirSync(cases, { recursive: true })
        const row = { t: Date.now() / 1000, text, harness: "opencode" }
        appendFileSync(join(cases, ".inbox.jsonl"), JSON.stringify(row) + "\n")
      } catch (_e) {}
    },
  }
}
