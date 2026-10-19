# Demo script

Start the services and open http://localhost:5173. Choose **Enter local workspace**. Check FULL MOCK, MOCK DISCOVERY and the simulated-email banner.

1. Choose **Find Suppliers**. The selected objective is **Sourcing Agent — BUY coffee**.
2. Use: “Find specialty coffee producers, exporters, or cooperatives in Ethiopia.” Country: Ethiopia.
3. Start discovery. Watch the checkpointed progress. PARTIAL is expected because Instagram and some other sources are unavailable.
4. Open **Dawn Ridge Producer Collective**, a fictional Ethiopian producer. It has no website; it remains eligible.
5. Open **Evidence**. Inspect the fictional source URLs, collection methods, dates and summaries.
6. Open **Score breakdown**. Initial fit is 90, with a separate MEDIUM confidence label and a versioned sourcing rubric.
7. Open **Human review**, add a note and choose **Approve candidate**.
8. Open **Outreach**, generate an email draft. Read the sourcing-specific request for lots, samples and an offer list.
9. Edit the message and save. The version increments and approval is pending. Approve that version, then choose **Send simulated email**. No network email is sent.
10. Open **Conversation** and simulate an interested reply mentioning an offer. Inspect OFFER_RECEIVED and the correction dropdown.
11. Optionally upload a UTF-8 CSV with columns `supplier,origin,lot,price,currency`. Inspect the extracted offer, correct it and save human review.
12. Open **Handoff**, create the summary. Repeating the request returns the same handoff.
13. View the audit trail and follow-up queue. Schedule a future follow-up, then simulate a new reply to demonstrate cancellation.

Lead demonstration: select **Find Buyers**, then use “Find potential buyers in Japan for high-quality Yemeni specialty coffee.” The result is **Kumo Atelier Coffee**, a fictional Japanese roaster. Outreach explores buying from Qima.

Other fictional seeds: Cloud Valley Exports (Colombia), High Terrace Growers (Yemen), Lantern Green Imports (UK), Copper Coast Distribution (US). All email addresses use reserved `.example` domains.

The Playwright test in `frontend/tests/e2e/sourcing.spec.ts` automates the critical sourcing-to-handoff journey. Run it with the API, worker and frontend already running. Repeated tests preserve the database and create additional draft/reply audit history; they do not wipe demo records.
