import { loadConfig } from "./config.ts";
import { createRouter, listen } from "./server.ts";

const cfg = loadConfig();
const server = createRouter(cfg);
const port = await listen(server, cfg.port, cfg.host);
console.log(JSON.stringify({ msg: "router up", host: cfg.host, port, encoder: cfg.encoderUrl, shards: cfg.shardGroups, shardTimeoutMs: cfg.shardTimeoutMs, hedgeMs: cfg.hedgeMs }));
for (const sig of ["SIGINT", "SIGTERM"] as const) process.on(sig, () => server.close(() => process.exit(0)));
