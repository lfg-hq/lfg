// ── Tool Collections ──────────────────────────────────────────────────────────

export { getProjectDashboard, setProjectStack, captureProjectName } from "./project-tools.ts";

export {
  streamDocumentContent,
  getFileList,
  getFileContent,
  updateFileContent,
  setWsBroadcast as setDocumentWsBroadcast,
} from "./document-tools.ts";

export {
  createTickets,
  getPendingTickets,
  getTicketDetails,
  updateTicket,
  updateTicketDetails,
  updateAllTickets,
  getNextTicket,
  scheduleTickets,
  retryTicket,
  sendTicketMessage,
  queueTicketExecution,
  setTicketWsBroadcast,
} from "./ticket-tools.ts";

export { getProjectEnvVars, registerRequiredEnvVars, setEnvVar } from "./env-tools.ts";

export {
  broadcastToUser,
  lookupTechnologySpecs,
  setWsBroadcast as setMiscWsBroadcast,
} from "./misc-tools.ts";

export { createInstantTools } from "./instant-tools.ts";

// ── tools_product: Full product analyst toolset ───────────────────────────────
import { getProjectDashboard, setProjectStack, captureProjectName } from "./project-tools.ts";
import { streamDocumentContent, getFileList, getFileContent, updateFileContent } from "./document-tools.ts";
import {
  createTickets, getPendingTickets, getTicketDetails,
  updateTicket, updateTicketDetails, updateAllTickets,
  getNextTicket, scheduleTickets, retryTicket, sendTicketMessage, queueTicketExecution,
} from "./ticket-tools.ts";
import { getProjectEnvVars, registerRequiredEnvVars, setEnvVar } from "./env-tools.ts";
import { broadcastToUser, lookupTechnologySpecs } from "./misc-tools.ts";

export const toolsProduct = {
  getProjectDashboard,
  setProjectStack,
  captureProjectName,
  streamDocumentContent,
  getFileList,
  getFileContent,
  updateFileContent,
  createTickets,
  getPendingTickets,
  getTicketDetails,
  updateTicket,
  updateTicketDetails,
  updateAllTickets,
  getNextTicket,
  scheduleTickets,
  retryTicket,
  sendTicketMessage,
  queueTicketExecution,
  getProjectEnvVars,
  registerRequiredEnvVars,
  setEnvVar,
  lookupTechnologySpecs,
  broadcastToUser,
};

// ── tools_turbo: Lightweight subset for quick interactions ────────────────────
export const toolsTurbo = {
  getProjectDashboard,
  getPendingTickets,
  getTicketDetails,
  updateTicket,
  sendTicketMessage,
  broadcastToUser,
};
