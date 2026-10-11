import { createInterface } from 'node:readline';

/** Feed complete JSONL commands to the already-authorized browser adapter. */
export async function runJsonlJourney(input, execute, record = async () => {}) {
  if (input.isTTY) throw new Error('Use a JSONL file through non-TTY stdin; terminal input can truncate commands.');
  if (typeof execute !== 'function' || typeof record !== 'function') throw new TypeError('Browser executor and recorder must be functions.');
  const lines = createInterface({ input, crlfDelay: Infinity, terminal: false });
  let line = 0, step = 0;
  try {
    for await (const text of lines) {
      line += 1;
      if (!text.trim()) continue;
      let command;
      try { command = JSON.parse(text); }
      catch { throw new Error(`Invalid journey JSON at line ${line}.`); }
      if (!command || typeof command !== 'object' || Array.isArray(command)) {
        throw new Error(`Journey line ${line} must be a JSON object.`);
      }
      step += 1;
      // The adapter owns allowed actions and must throw on an error or an
      // unconfirmed required result. Never dispatch a later step after failure.
      const result = await execute(command);
      await record({ step, line, command, result });
    }
    return { steps: step, lines: line };
  } finally {
    lines.close();
  }
}
