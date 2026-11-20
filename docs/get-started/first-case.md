# Your first case

This walkthrough takes one application from submission to a recorded decision. It assumes the stack is running ([Deploy with Docker](deploy.md)) and the console is open at
`http://127.0.0.1:8501`.

## 1. Check that everything is ready

The sidebar shows **All services running** when every required component is available. If it does not, run:

```bash
docker compose exec console wealthpilot doctor
```

The command lists each component and the fix for anything missing.

## 2. Tell the console who you are

In the sidebar, under **Signed in as**, enter your name or id and choose your authority tier (Analyst, Senior Credit Officer or Credit Committee). The name is recorded with every decision you
make, and your tier is used to pre-fill the decision form.

## 3. Submit an application

1. Open **New case**.
2. Enter the business and loan details. The principal owner needs a first and last name.
3. Upload the applicant's **financial statements** and **bank statement** as PDFs.
4. Choose the **credit policy** to apply.
5. Select **Run underwriting**.

!!! note "No documents at hand?"
    In demonstration mode the page also offers **Try a sample applicant**, which runs a ready-made example. See [Deploy with Docker](deploy.md#demonstration-mode).

The case starts at once and a progress bar shows each step. A run takes a few minutes. You can leave the page: the case continues in the background and appears in your **Inbox** when it needs you.

## 4. Review the evidence

Open the case from the Inbox. The header shows the recommendation, the risk grade, the five-year default probability and the approval tier the policy requires. The tabs hold the evidence:

* **Memo**: the written recommendation with strengths, concerns and, for a decline, the adverse-action reasons.
* **Policy checklist**: every rule with its status, the reason, and the sentence quoted from the policy.
* **Financials**: the extracted statements, the ratios beside the policy limits, a stress test and bank balances.
* **Risk**: the default probability, the main risk factors and the scorecard.
* **Research**: sanctions screening, adverse media and registry results.

## 5. Record your decision

Below the evidence, choose **approve**, **decline** or **revise**, add your comments, and select **Submit decision**. A reason is required if you go against the recommendation or ask for a revision, and you cannot decide a
case that needs a higher authority tier than yours.

## 6. Check the audit trail

Open **History**. The decision is listed with its recommendation, whether it overrode the recommendation, your name and tier, and the integrity banner confirms the audit chain is intact.

For the full description of every page, see [Using the console](../user-guide/console.md).
