import time
from app.db import get_db, init_db
from app.config import compute_prompt_hash, DEFAULT_TRIAGE_PROMPT

def seed_demo_emails():
    init_db()
    prompt_hash = compute_prompt_hash(DEFAULT_TRIAGE_PROMPT)
    now = int(time.time())

    demo_data = [
        {
            "id": "msg_google_sec",
            "thread_id": "th_google_sec",
            "sender_name": "Google",
            "sender_email": "no-reply@accounts.google.com",
            "account": "abhed8604@gmail.com",
            "subject": "Security alert: New sign-in on Linux device",
            "date_str": "Sun, 18 Oct 2026 21:40:12 +0530",
            "timestamp": now - 3600 * 1,
            "label": "very_important",
            "confidence": 0.98,
            "unread": 1,
            "model_input": (
                "From: Google <no-reply@accounts.google.com>\n"
                "Subject: Security alert: New sign-in on Linux device\n\n"
                "Your Google Account abhed8604@gmail.com was just signed in to from a new Linux device in Ranchi, Jharkhand, India. "
                "If this was you, you don't need to do anything. If not, check your recent security activity immediately."
            ),
            "body_text": (
                "Google Security Alert\n\n"
                "New sign-in on Linux\n"
                "Account: abhed8604@gmail.com\n\n"
                "We noticed a new sign-in to your Google Account on a Linux device. If this was you, you don't need to do anything.\n\n"
                "Details:\n"
                "• Device: Linux x86_64\n"
                "• Location: Ranchi, Jharkhand, India (Approximate based on IP)\n"
                "• IP address: 103.212.144.18\n"
                "• Time: October 18, 2026, 9:40 PM IST\n\n"
                "If you did not sign in recently, please secure your account immediately:\n"
                "https://myaccount.google.com/notifications\n\n"
                "— The Google Accounts Team"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; color: #202124; line-height: 1.5;">
              <div style="padding: 24px 0 16px; border-bottom: 1px solid #e0e0e0;">
                <span style="font-size: 22px; font-weight: 600; color: #1a73e8; letter-spacing: -0.5px;">Google</span>
              </div>
              <div style="padding: 28px 0 20px;">
                <h1 style="font-size: 20px; font-weight: 500; margin: 0 0 14px; color: #d93025;">Security alert: New sign-in on Linux</h1>
                <p style="font-size: 14px; color: #3c4043; margin: 0 0 18px;">Your Google Account <strong>abhed8604@gmail.com</strong> was recently accessed from a new device.</p>
                <div style="background: #f8f9fa; border: 1px solid #dadce0; border-radius: 12px; padding: 18px; margin-bottom: 24px;">
                  <table style="width: 100%; font-size: 13.5px; border-collapse: collapse;">
                    <tr><td style="padding: 6px 0; color: #5f6368; width: 110px;">Device</td><td style="padding: 6px 0; font-weight: 500;">Linux Desktop (Ubuntu 24.04 LTS)</td></tr>
                    <tr><td style="padding: 6px 0; color: #5f6368;">Location</td><td style="padding: 6px 0; font-weight: 500;">Ranchi, Jharkhand, India</td></tr>
                    <tr><td style="padding: 6px 0; color: #5f6368;">IP Address</td><td style="padding: 6px 0; font-weight: 500; font-family: monospace;">103.212.144.18</td></tr>
                    <tr><td style="padding: 6px 0; color: #5f6368;">Time</td><td style="padding: 6px 0; font-weight: 500;">Oct 18, 2026, 9:40 PM IST</td></tr>
                  </table>
                </div>
                <a href="#" style="display: inline-block; background: #1a73e8; color: #ffffff; text-decoration: none; padding: 10px 22px; border-radius: 6px; font-weight: 500; font-size: 14px;">Check Activity</a>
              </div>
              <div style="border-top: 1px solid #e0e0e0; padding-top: 16px; font-size: 12px; color: #5f6368;">
                You received this mandatory email service announcement to update you about important changes to your Google Account.
              </div>
            </div>
            """
        },
        {
            "id": "msg_cisco_invite",
            "thread_id": "th_cisco_invite",
            "sender_name": "Talent Acquisition Cisco",
            "sender_email": "campus-recruitment@cisco.com",
            "account": "abhed.student@bitmesra.ac.in",
            "subject": "Invitation: Technical Assessment & System Design Round - Abhed",
            "date_str": "Sun, 18 Oct 2026 19:15:00 +0530",
            "timestamp": now - 3600 * 3,
            "label": "very_important",
            "confidence": 0.96,
            "unread": 1,
            "model_input": (
                "From: Talent Acquisition Cisco <campus-recruitment@cisco.com>\n"
                "Subject: Invitation: Technical Assessment & System Design Round - Abhed\n\n"
                "Dear Abhed, Based on your resume screening for the Software Engineer - Systems & Cloud role at Cisco Bangalore, "
                "you are shortlisted for the technical assessment on HackerRank. Test window closes Oct 21, 2026, 11:59 PM IST."
            ),
            "body_text": (
                "Dear Abhed,\n\n"
                "Congratulations! Following your application via the BIT Mesra Training & Placement Cell, we are pleased to invite you "
                "to take the Cisco Online Technical Assessment for the Software Engineer - Cloud & Systems Infrastructure role.\n\n"
                "Assessment Overview:\n"
                "• Platform: HackerRank CodePair\n"
                "• Duration: 90 Minutes (2 Data Structures & Algorithms questions + 1 Systems/Networking case scenario)\n"
                "• Test Window Closes: Wednesday, October 21, 2026 at 23:59 IST\n"
                "• Allowed Languages: C++, Python 3, Go, Java\n\n"
                "Access your unique test link here:\n"
                "https://assess.hackerrank.com/cisco/invite/c7f901abhed8604\n\n"
                "Important Guidelines:\n"
                "1. Ensure you have a functioning webcam and a stable internet connection.\n"
                "2. Plagiarism detection algorithms and proctoring will be strictly enforced.\n\n"
                "Best regards,\n"
                "University Relations & Talent Acquisition\n"
                "Cisco Systems India Pvt Ltd"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; color: #222; line-height: 1.6;">
              <div style="background: #049fd9; padding: 20px 24px; border-radius: 8px 8px 0 0; color: white;">
                <h2 style="margin: 0; font-size: 20px; font-weight: 600;">Cisco University Talent Acquisition</h2>
                <p style="margin: 4px 0 0; opacity: 0.9; font-size: 13px;">Campus Hiring 2026 · BIT Mesra</p>
              </div>
              <div style="background: #ffffff; padding: 24px; border: 1px solid #dcdcdc; border-top: none; border-radius: 0 0 8px 8px;">
                <p style="font-size: 15px; margin-top: 0;">Dear <strong>Abhed</strong>,</p>
                <p>We are pleased to inform you that you have been shortlisted for the <strong>Online Technical Assessment</strong> for the Software Engineer (Systems & Cloud) position at Cisco Bangalore.</p>
                <div style="background: #f0f8ff; border-left: 4px solid #049fd9; padding: 14px 18px; margin: 20px 0; border-radius: 0 6px 6px 0;">
                  <p style="margin: 0 0 6px; font-size: 13.5px;"><strong>Duration:</strong> 90 minutes (2 Coding + 1 System scenario)</p>
                  <p style="margin: 0 0 6px; font-size: 13.5px;"><strong>Deadline:</strong> Wednesday, Oct 21, 2026, 11:59 PM IST</p>
                  <p style="margin: 0; font-size: 13.5px;"><strong>Platform:</strong> HackerRank Campus Pro</p>
                </div>
                <p style="margin: 22px 0 24px;">
                  <a href="#" style="background: #049fd9; color: #fff; text-decoration: none; padding: 11px 24px; border-radius: 6px; font-weight: 600; display: inline-block;">Start Assessment</a>
                </p>
                <p style="font-size: 12.5px; color: #666; margin-bottom: 0;">Please ensure camera permissions are granted. For technical issues during testing, contact support@hackerrank.com.</p>
              </div>
            </div>
            """
        },
        {
            "id": "msg_gh_ci_fail",
            "thread_id": "th_gh_ci_fail",
            "sender_name": "GitHub Notifications",
            "sender_email": "notifications@github.com",
            "account": "abhed.work@inboxzen.dev",
            "subject": "[inboxzen/core] Run failed: Build & Test (commit #9a4f21d)",
            "date_str": "Sun, 18 Oct 2026 17:30:22 +0530",
            "timestamp": now - 3600 * 5,
            "label": "important",
            "confidence": 0.94,
            "unread": 1,
            "model_input": (
                "From: GitHub <notifications@github.com>\n"
                "Subject: [inboxzen/core] Run failed: Build & Test\n\n"
                "Commit 9a4f21d by abhed8604\n"
                "Workflow: Python CI / Test Suite (Linux x86_64)\n"
                "Status: Failure in step 'pytest tests/test_classifier.py::test_vram_limit'. Exited with code 1."
            ),
            "body_text": (
                "GitHub Actions: Run failed for main (commit 9a4f21d)\n\n"
                "Repository: inboxzen/core\n"
                "Workflow: Python CI / Test Suite\n"
                "Triggered by: abhed8604 (feat: tune flash attention microbatch size)\n\n"
                "Failed Step: Run pytest test suite\n"
                "Error:\n"
                "FAILED tests/test_classifier.py::test_vram_limit - AssertionError: Expected VRAM peak <= 1180MB, found 1240MB\n"
                "1 failed, 42 passed in 4.82s\n\n"
                "View workflow run details:\n"
                "https://github.com/inboxzen/core/actions/runs/18940182\n"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; color: #24292f;">
              <div style="border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden;">
                <div style="background: #ffebe9; border-bottom: 1px solid rgba(255, 129, 130, 0.4); padding: 14px 20px; display: flex; align-items: center;">
                  <span style="background: #cf222e; color: white; border-radius: 50%; width: 22px; height: 22px; display: inline-flex; align-items: center; justify-content: center; font-size: 13px; font-weight: bold; margin-right: 10px;">✕</span>
                  <span style="font-weight: 600; color: #cf222e; font-size: 14px;">Build &amp; Test failed on main</span>
                </div>
                <div style="padding: 20px;">
                  <p style="margin: 0 0 10px; font-size: 14px;"><strong>inboxzen/core</strong> commit <code style="background: #f6f8fa; padding: 2px 5px; border-radius: 4px;">9a4f21d</code></p>
                  <p style="margin: 0 0 16px; color: #57609a; font-size: 13px;">Author: abhed8604 · Message: "feat: tune flash attention microbatch size"</p>
                  <div style="background: #24292f; color: #f0f6fc; padding: 12px 14px; border-radius: 6px; font-family: monospace; font-size: 12px; margin-bottom: 18px; overflow-x: auto;">
                    FAILED tests/test_classifier.py::test_vram_limit<br/>
                    AssertionError: Expected VRAM peak &lt;= 1180MB, found 1240MB
                  </div>
                  <a href="#" style="background: #2da44e; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 6px; font-weight: 600; font-size: 13px; display: inline-block;">View Workflow Run</a>
                </div>
              </div>
            </div>
            """
        },
        {
            "id": "msg_bit_tnp",
            "thread_id": "th_bit_tnp",
            "sender_name": "Training & Placement Cell · BIT Mesra",
            "sender_email": "tnp@bitmesra.ac.in",
            "account": "abhed.student@bitmesra.ac.in",
            "subject": "URGENT: Shortlisted Students for Microsoft IDC Interviews & Verification",
            "date_str": "Sun, 18 Oct 2026 15:00:10 +0530",
            "timestamp": now - 3600 * 8,
            "label": "very_important",
            "confidence": 0.99,
            "unread": 1,
            "model_input": (
                "From: Training & Placement Cell <tnp@bitmesra.ac.in>\n"
                "Subject: URGENT: Shortlisted Students for Microsoft IDC Interviews\n\n"
                "All shortlisted candidates for Microsoft IDC Software Engineer 2026 batch must report to CAT Hall by 8:30 AM tomorrow "
                "in formal attire with 3 hard copies of verified resume and student ID card."
            ),
            "body_text": (
                "Circular No: BIT/TnP/2026/894\n"
                "Date: 18 October 2026\n\n"
                "ATTENTION: 2026 Batch B.Tech (CSE, IT, ECE)\n\n"
                "Subject: Microsoft India Development Centre (IDC) - Interview Schedule & Document Verification\n\n"
                "The following shortlisted students (including Abhed - Roll: BTECH/10042/22) are hereby directed to report "
                "to the CAT Hall at the Main Building tomorrow morning at 8:30 AM sharp.\n\n"
                "Mandatory Checklist:\n"
                "1. Three copies of verified resume with T&P stamp\n"
                "2. College Identity Card and Government ID (Aadhaar / Passport)\n"
                "3. College formal dress code strictly required\n"
                "4. Personal laptops with fully charged batteries and hot-spot backup for live pair coding rounds\n\n"
                "Failure to report on time will lead to immediate cancellation of candidature.\n\n"
                "Dr. B. K. Singh\n"
                "Professor In-Charge, Training & Placement Cell\n"
                "Birla Institute of Technology, Mesra, Ranchi"
            ),
            "body_html": """
            <div style="font-family: Georgia, serif; max-width: 620px; margin: 0 auto; color: #1a1a1a; line-height: 1.6; border: 1px solid #c9c9c9; padding: 28px; background: #fff;">
              <div style="text-align: center; border-bottom: 2px solid #8b0000; padding-bottom: 16px; margin-bottom: 20px;">
                <h2 style="margin: 0; color: #8b0000; font-size: 21px; text-transform: uppercase;">Birla Institute of Technology, Mesra</h2>
                <h4 style="margin: 4px 0 0; color: #444; font-weight: normal; font-size: 14px;">Training &amp; Placement Division · Ranchi - 835215</h4>
              </div>
              <p style="font-size: 13px; color: #666;">Ref: BIT/TnP/2026/894 <span style="float: right;">Date: 18.10.2026</span></p>
              <h3 style="font-size: 16px; color: #8b0000; margin: 16px 0 10px;">URGENT: Microsoft IDC Final Round Interviews</h3>
              <p>Shortlisted candidates for Microsoft IDC Software Engineer 2026 must report to <strong>CAT Hall</strong> tomorrow at <strong>8:30 AM IST</strong>.</p>
              <ul style="padding-left: 20px; font-size: 14px;">
                <li>Three hard copies of stamped resume</li>
                <li>Institute ID and valid government photo ID</li>
                <li>Full formal dress code</li>
                <li>Fully charged laptop for live code pairing</li>
              </ul>
              <p style="font-size: 13px; color: #555; margin-top: 24px;">Dr. B. K. Singh<br/><em>Head, Training &amp; Placement Cell</em></p>
            </div>
            """
        },
        {
            "id": "msg_stripe_payout",
            "thread_id": "th_stripe_payout",
            "sender_name": "Stripe",
            "sender_email": "notifications@stripe.com",
            "account": "abhed.work@inboxzen.dev",
            "subject": "Your $1,420.00 USD payout is on its way to your bank account",
            "date_str": "Sat, 17 Oct 2026 22:10:00 +0530",
            "timestamp": now - 3600 * 24,
            "label": "very_important",
            "confidence": 0.95,
            "unread": 1,
            "model_input": (
                "From: Stripe <notifications@stripe.com>\n"
                "Subject: Your $1,420.00 USD payout is on its way\n\n"
                "A payout of $1,420.00 USD was initiated on October 17, 2026 for InboxZen Pro subscriptions. "
                "Funds are expected in your HDFC account ending in 4108 within 1-2 business days."
            ),
            "body_text": (
                "Your payout is on the way.\n\n"
                "Amount: $1,420.00 USD\n"
                "Expected arrival: Monday, October 19, 2026\n"
                "Destination: HDFC Bank Ltd •••• 4108\n"
                "Transfer ID: po_1OtKq2Lkd9vQx87291a\n\n"
                "Summary:\n"
                "• Gross volume: $1,480.00\n"
                "• Stripe processing fees: -$60.00\n"
                "• Net payout: $1,420.00\n\n"
                "View this transfer in your Stripe Dashboard:\n"
                "https://dashboard.stripe.com/payouts/po_1OtKq2Lkd9vQx87291a"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; color: #3c4257;">
              <div style="background: #ffffff; border: 1px solid #e3e8ee; border-radius: 8px; padding: 28px;">
                <span style="font-size: 20px; font-weight: 700; color: #635bff;">stripe</span>
                <h2 style="font-size: 19px; color: #0a2540; margin: 18px 0 8px;">$1,420.00 USD is on its way</h2>
                <p style="color: #4f566b; font-size: 14px; margin: 0 0 20px;">Payout initiated for InboxZen Software account.</p>
                <div style="background: #f8fbfd; border: 1px solid #e3e8ee; border-radius: 6px; padding: 16px; margin-bottom: 22px;">
                  <div style="display: flex; justify-content: space-between; font-size: 13.5px; padding: 4px 0;">
                    <span style="color: #697386;">Destination</span>
                    <span style="font-weight: 500;">HDFC Bank •••• 4108</span>
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 13.5px; padding: 4px 0;">
                    <span style="color: #697386;">Estimated arrival</span>
                    <span style="font-weight: 500;">Oct 19, 2026</span>
                  </div>
                  <div style="display: flex; justify-content: space-between; font-size: 13.5px; padding: 4px 0;">
                    <span style="color: #697386;">Transfer ID</span>
                    <span style="font-family: monospace; font-size: 12px;">po_1OtKq2Lkd9v</span>
                  </div>
                </div>
                <a href="#" style="background: #635bff; color: #fff; text-decoration: none; padding: 9px 18px; border-radius: 5px; font-weight: 500; font-size: 13px; display: inline-block;">View in Dashboard</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_linear_digest",
            "thread_id": "th_linear_digest",
            "sender_name": "Linear",
            "sender_email": "updates@linear.app",
            "account": "abhed.work@inboxzen.dev",
            "subject": "InboxZen Sprint #4: 18 issues completed, 3 blocked in triage",
            "date_str": "Sat, 17 Oct 2026 18:45:00 +0530",
            "timestamp": now - 3600 * 28,
            "label": "important",
            "confidence": 0.91,
            "unread": 1,
            "model_input": (
                "From: Linear <updates@linear.app>\n"
                "Subject: InboxZen Sprint #4: 18 issues completed\n\n"
                "Weekly summary for team Engineering: Cycle 4 velocity was 46 points (+12%). "
                "Top contributors: @abhed (12 issues closed). Blocked tasks: Ollama vs llama.cpp latency benchmarks."
            ),
            "body_text": (
                "Linear Cycle #4 Report · InboxZen\n\n"
                "Completed Issues (18):\n"
                "• INBOX-41: Fix flash attention CUDA out of memory on 4GB VRAM\n"
                "• INBOX-39: Transition SQLite storage to WAL mode for 10x query throughput\n"
                "• INBOX-37: Implement unread toggle and real-time dot pulsation\n"
                "• INBOX-36: Sandbox email reader iframe with strict CSP\n\n"
                "In Progress / Blocked (3):\n"
                "• INBOX-44: Multi-account OAuth token rotation (Blocked by Google Cloud Review)\n\n"
                "Cycle Velocity: 46 points completed (+12% vs previous cycle)"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; color: #222;">
              <div style="background: #12151c; color: #fff; padding: 20px 24px; border-radius: 8px 8px 0 0;">
                <h3 style="margin: 0; font-size: 18px; font-weight: 600;">Linear · Cycle 4 Summary</h3>
                <p style="margin: 4px 0 0; color: #8a8f98; font-size: 13px;">Team Engineering · 18 issues closed</p>
              </div>
              <div style="border: 1px solid #e1e4ea; border-top: none; padding: 22px; border-radius: 0 0 8px 8px; background: #fff;">
                <div style="margin-bottom: 16px;">
                  <span style="font-size: 13px; font-weight: 600; color: #5e6ad2; text-transform: uppercase;">Completed Highlights</span>
                  <p style="font-size: 13.5px; margin: 6px 0;">✓ <strong>INBOX-41:</strong> Fix flash attention CUDA OOM on GTX 1650</p>
                  <p style="font-size: 13.5px; margin: 6px 0;">✓ <strong>INBOX-39:</strong> SQLite WAL mode migration</p>
                  <p style="font-size: 13.5px; margin: 6px 0;">✓ <strong>INBOX-37:</strong> Pulse dot and unread email contrast</p>
                </div>
                <a href="#" style="color: #5e6ad2; text-decoration: none; font-size: 13px; font-weight: 500;">Open Linear Board →</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_swiggy_receipt",
            "thread_id": "th_swiggy_receipt",
            "sender_name": "Swiggy",
            "sender_email": "order@swiggy.in",
            "account": "abhed8604@gmail.com",
            "subject": "Delivered: Your food order from Meghana Foods is complete",
            "date_str": "Sat, 17 Oct 2026 13:20:00 +0530",
            "timestamp": now - 3600 * 33,
            "label": "low_priority",
            "confidence": 0.97,
            "unread": 0,
            "model_input": (
                "From: Swiggy <order@swiggy.in>\n"
                "Subject: Delivered: Your food order from Meghana Foods\n\n"
                "Your order #1892837192 has been delivered by Mahesh K. Total: ₹489.00 paid via Google Pay UPI. "
                "View detailed bill and download tax invoice."
            ),
            "body_text": (
                "Swiggy Delivery Confirmation\n\n"
                "Order #1892837192\n"
                "Restaurant: Meghana Foods, Indiranagar\n"
                "Delivered to: Abhed · Flat 402, Green Glen Layout\n\n"
                "Items Ordered:\n"
                "1x Special Chicken Biryani (Boneless) - ₹395.00\n"
                "1x Extra Raita (200ml) - ₹30.00\n\n"
                "Billing Details:\n"
                "Item Total: ₹425.00\n"
                "GST & Restaurant Charges: ₹29.00\n"
                "Delivery Fee: ₹35.00\n"
                "Discount Applied (SWIGGYIT): -₹0.00\n"
                "Total Paid: ₹489.00 (via UPI)\n\n"
                "Hope you enjoyed your meal! Rate your delivery partner in the Swiggy app."
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 540px; margin: 0 auto; color: #282c3f;">
              <div style="background: #fc8019; padding: 18px 24px; color: white; border-radius: 8px 8px 0 0;">
                <h3 style="margin: 0; font-size: 20px; font-weight: 700;">swiggy</h3>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Order Delivered · Meghana Foods</p>
              </div>
              <div style="border: 1px solid #e9e9eb; border-top: none; padding: 22px; border-radius: 0 0 8px 8px; background: #fff;">
                <h4 style="margin: 0 0 12px; font-size: 15px;">Order Summary (#1892837192)</h4>
                <div style="font-size: 13.5px; border-bottom: 1px dashed #e9e9eb; padding-bottom: 12px; margin-bottom: 12px;">
                  <div style="display: flex; justify-content: space-between; padding: 3px 0;">
                    <span>1x Special Chicken Biryani</span>
                    <span style="font-weight: 500;">₹395.00</span>
                  </div>
                  <div style="display: flex; justify-content: space-between; padding: 3px 0;">
                    <span>1x Extra Raita</span>
                    <span style="font-weight: 500;">₹30.00</span>
                  </div>
                </div>
                <div style="display: flex; justify-content: space-between; font-weight: 700; font-size: 15px;">
                  <span>Total Paid (UPI)</span>
                  <span>₹489.00</span>
                </div>
              </div>
            </div>
            """
        },
        {
            "id": "msg_amazon_delivery",
            "thread_id": "th_amazon_delivery",
            "sender_name": "Amazon.in",
            "sender_email": "shipment-tracking@amazon.in",
            "account": "abhed8604@gmail.com",
            "subject": "Out for delivery: 'Crucial P3 Plus 1TB PCIe 4.0 3D NAND NVMe M.2 SSD'",
            "date_str": "Sat, 17 Oct 2026 10:05:00 +0530",
            "timestamp": now - 3600 * 36,
            "label": "important",
            "confidence": 0.93,
            "unread": 1,
            "model_input": (
                "From: Amazon.in <shipment-tracking@amazon.in>\n"
                "Subject: Out for delivery: Crucial P3 Plus 1TB PCIe NVMe SSD\n\n"
                "Your package is out for delivery today with associate Rahul S. Your delivery OTP is 491823. "
                "Please share this OTP with the delivery agent upon receiving the package."
            ),
            "body_text": (
                "Amazon.in Delivery Update\n\n"
                "Order #408-1928491-9281729\n"
                "Item: Crucial P3 Plus 1TB PCIe 4.0 3D NAND NVMe M.2 SSD, up to 5000MB/s\n\n"
                "Status: OUT FOR DELIVERY\n"
                "Expected delivery: Today by 3:00 PM\n"
                "Delivery Associate: Rahul S. (98450*****)\n\n"
                "YOUR DELIVERY OTP IS: 491823\n"
                "Please share this OTP only when you physically receive your order.\n\n"
                "Track your package on Amazon:\n"
                "https://www.amazon.in/gp/your-account/order-history"
            ),
            "body_html": """
            <div style="font-family: Arial, sans-serif; max-width: 580px; margin: 0 auto; color: #111;">
              <div style="background: #232f3e; padding: 16px 20px; color: white;">
                <h3 style="margin: 0; color: #ff9900; font-size: 20px;">amazon.in</h3>
              </div>
              <div style="border: 1px solid #ddd; padding: 22px; background: #fff;">
                <h2 style="font-size: 17px; color: #007600; margin: 0 0 10px;">Out for delivery today</h2>
                <p style="font-size: 14px; margin: 0 0 16px;">Crucial P3 Plus 1TB PCIe 4.0 3D NAND NVMe M.2 SSD</p>
                <div style="background: #fff8e7; border: 1px solid #fbd88a; padding: 14px 18px; border-radius: 6px; text-align: center; margin-bottom: 20px;">
                  <span style="font-size: 13px; color: #555; display: block; margin-bottom: 4px;">YOUR DELIVERY OTP</span>
                  <span style="font-size: 26px; font-weight: bold; letter-spacing: 4px; color: #111;">491823</span>
                </div>
                <p style="font-size: 13px; color: #555;">Share this OTP with the driver only upon receiving the parcel.</p>
              </div>
            </div>
            """
        },
        {
            "id": "msg_aws_alert",
            "thread_id": "th_aws_alert",
            "sender_name": "Amazon Web Services",
            "sender_email": "no-reply-aws@amazon.com",
            "account": "abhed.work@inboxzen.dev",
            "subject": "ALARM: 'Monthly-Budget-Limit' threshold reached 85% ($85.40 of $100.00)",
            "date_str": "Fri, 16 Oct 2026 20:15:30 +0530",
            "timestamp": now - 3600 * 50,
            "label": "very_important",
            "confidence": 0.96,
            "unread": 1,
            "model_input": (
                "From: AWS CloudWatch <no-reply-aws@amazon.com>\n"
                "Subject: ALARM: Monthly-Budget-Limit reached 85%\n\n"
                "You are receiving this because your AWS account budget alert triggered in region ap-south-1 (Mumbai). "
                "Current forecasted cost is $102.30. Main driver: EC2 g4dn.xlarge GPU on-demand instances."
            ),
            "body_text": (
                "AWS Budgets Notification\n\n"
                "Account ID: 8912-4019-3810\n"
                "Budget Name: Monthly-Budget-Limit\n"
                "Notification Type: ACTUAL > 85%\n\n"
                "Budget Amount: $100.00 USD\n"
                "Current Spend: $85.40 USD (85.4%)\n"
                "Forecasted Spend: $102.30 USD (102.3%)\n\n"
                "Top contributing services:\n"
                "1. Amazon Elastic Compute Cloud (EC2): $72.10 (g4dn.xlarge instance running)\n"
                "2. Amazon Simple Storage Service (S3): $8.20\n"
                "3. AWS Key Management Service (KMS): $5.10\n\n"
                "Manage your budget in AWS Billing Console:\n"
                "https://console.aws.amazon.com/billing/home#/budgets"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; color: #16191f;">
              <div style="background: #232f3e; padding: 16px 20px; color: #ff9900; font-size: 18px; font-weight: bold;">AWS Budgets</div>
              <div style="border: 1px solid #eaeded; padding: 22px; background: #fff;">
                <h3 style="color: #d13212; margin: 0 0 12px; font-size: 16px;">Budget Threshold Exceeded (85%)</h3>
                <p style="font-size: 14px; margin: 0 0 16px;">Your monthly budget limit of <strong>$100.00 USD</strong> has reached <strong>$85.40 USD</strong>.</p>
                <div style="background: #fafafa; border: 1px solid #e1e4ea; border-radius: 6px; padding: 14px; margin-bottom: 18px; font-size: 13px;">
                  <div style="display: flex; justify-content: space-between; padding: 3px 0;">
                    <span>Primary Cost Driver</span>
                    <strong>EC2 g4dn.xlarge ($72.10)</strong>
                  </div>
                  <div style="display: flex; justify-content: space-between; padding: 3px 0;">
                    <span>Forecasted Month End</span>
                    <strong style="color: #d13212;">$102.30 USD</strong>
                  </div>
                </div>
                <a href="#" style="background: #ec7211; color: #fff; text-decoration: none; padding: 9px 18px; border-radius: 4px; font-size: 13px; font-weight: 500; display: inline-block;">View AWS Cost Explorer</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_acm_seminar",
            "thread_id": "th_acm_seminar",
            "sender_name": "ACM BIT Mesra Student Chapter",
            "sender_email": "acm@bitmesra.ac.in",
            "account": "abhed.student@bitmesra.ac.in",
            "subject": "Workshop this Friday: Compiling Local LLMs with llama.cpp and CUDA",
            "date_str": "Fri, 16 Oct 2026 16:00:00 +0530",
            "timestamp": now - 3600 * 54,
            "label": "important",
            "confidence": 0.89,
            "unread": 0,
            "model_input": (
                "From: ACM BIT Mesra <acm@bitmesra.ac.in>\n"
                "Subject: Workshop: Compiling Local LLMs with llama.cpp and CUDA\n\n"
                "Join us this Friday at 5:00 PM in Computer Lab 3. We will cover CMake compilation flags for NVIDIA Turing GPUs, "
                "GGUF Q4_K_M vs Q8_0 quantizations, and running inference with flash-attention."
            ),
            "body_text": (
                "ACM Student Chapter · Birla Institute of Technology Mesra\n\n"
                "Tech Talk & Hands-on Workshop:\n"
                "'Running Edge LLMs on Consumer GPUs with llama.cpp and CUDA'\n\n"
                "When: Friday, October 23, 2026 | 5:00 PM - 7:00 PM IST\n"
                "Where: Computer Science Lab 3, Department of CSE\n"
                "Speaker: Abhed (Final Year CSE)\n\n"
                "Key Topics:\n"
                "1. Compiling llama.cpp with LLAMA_CUDA=ON and nvcc optimizations\n"
                "2. Memory footprints: KV cache allocation and context micro-batching\n"
                "3. Evaluating vllm-d3-lite with strict grammar constrained generation\n\n"
                "Open to all students. Bring your laptop with Linux or WSL2."
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; color: #222;">
              <div style="background: #0075a2; padding: 20px 24px; color: #fff; border-radius: 8px 8px 0 0;">
                <h3 style="margin: 0; font-size: 18px;">ACM BIT Mesra Chapter</h3>
                <p style="margin: 4px 0 0; font-size: 13px; opacity: 0.9;">Hands-on Technical Session</p>
              </div>
              <div style="border: 1px solid #d0d7de; border-top: none; padding: 22px; border-radius: 0 0 8px 8px; background: #fff;">
                <h2 style="font-size: 17px; margin: 0 0 8px; color: #0075a2;">Compiling Local LLMs with llama.cpp &amp; CUDA</h2>
                <p style="font-size: 13.5px; color: #555; margin: 0 0 14px;">Friday, Oct 23 · 5:00 PM · CSE Lab 3</p>
                <p style="font-size: 14px; line-height: 1.5;">Learn how to compile and run GGUF quantized models locally with zero memory bloat on standard 4GB NVIDIA GPUs.</p>
              </div>
            </div>
            """
        },
        {
            "id": "msg_linkedin_digest",
            "thread_id": "th_linkedin_digest",
            "sender_name": "LinkedIn Job Alerts",
            "sender_email": "jobalerts-noreply@linkedin.com",
            "account": "abhed8604@gmail.com",
            "subject": "12 new jobs for 'Junior ML Engineer' and 'Backend Developer'",
            "date_str": "Fri, 16 Oct 2026 09:30:00 +0530",
            "timestamp": now - 3600 * 62,
            "label": "low_priority",
            "confidence": 0.98,
            "unread": 0,
            "model_input": (
                "From: LinkedIn Job Alerts <jobalerts-noreply@linkedin.com>\n"
                "Subject: 12 new jobs for Junior ML Engineer and Backend Developer\n\n"
                "Top matches based on your profile: Razorpay (Bengaluru) - SDE 1 Python/Go; BrowserStack (Mumbai) - Systems Engineer; "
                "Flipkart (Bengaluru) - Software Development Engineer 1."
            ),
            "body_text": (
                "LinkedIn Job Alerts for Abhed\n\n"
                "12 new opportunities match your alert criteria:\n\n"
                "1. Razorpay · Bengaluru, Karnataka (Hybrid)\n"
                "   Software Development Engineer 1 - Python/Go\n"
                "   Actively recruiting · 3 alumni work here\n\n"
                "2. BrowserStack · Mumbai, Maharashtra (Remote)\n"
                "   Junior Systems Engineer - Infrastructure & Linux\n"
                "   Easy Apply available\n\n"
                "3. Flipkart · Bengaluru, Karnataka (On-site)\n"
                "   SDE 1 - Catalog & Search Platforms\n\n"
                "See all 12 job openings on LinkedIn:\n"
                "https://www.linkedin.com/jobs"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; color: #000000e6;">
              <div style="padding: 16px 20px; border-bottom: 1px solid #e0e0e0;">
                <span style="font-size: 20px; font-weight: bold; color: #0a66c2;">Linked<span style="background: #0a66c2; color: #fff; padding: 0 4px; border-radius: 3px;">in</span></span>
              </div>
              <div style="padding: 20px;">
                <h3 style="font-size: 16px; margin: 0 0 14px;">12 new jobs match your preferences</h3>
                <div style="border-bottom: 1px solid #f3f3f3; padding-bottom: 12px; margin-bottom: 12px;">
                  <strong style="font-size: 14.5px; color: #0a66c2;">Software Development Engineer 1</strong>
                  <div style="font-size: 13px; color: #666;">Razorpay · Bengaluru (Hybrid)</div>
                </div>
                <div style="border-bottom: 1px solid #f3f3f3; padding-bottom: 12px; margin-bottom: 12px;">
                  <strong style="font-size: 14.5px; color: #0a66c2;">Junior Systems Engineer</strong>
                  <div style="font-size: 13px; color: #666;">BrowserStack · Remote</div>
                </div>
                <a href="#" style="background: #0a66c2; color: #fff; text-decoration: none; padding: 8px 16px; border-radius: 16px; font-size: 13px; font-weight: 600; display: inline-block;">View Jobs</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_zomato_promo",
            "thread_id": "th_zomato_promo",
            "sender_name": "Zomato Gold",
            "sender_email": "promotions@zomato.com",
            "account": "abhed8604@gmail.com",
            "subject": "Weekend craving? Flat 40% OFF up to ₹100 on dining out",
            "date_str": "Thu, 15 Oct 2026 19:40:00 +0530",
            "timestamp": now - 3600 * 76,
            "label": "low_priority",
            "confidence": 0.99,
            "unread": 0,
            "model_input": (
                "From: Zomato Gold <promotions@zomato.com>\n"
                "Subject: Weekend craving? Flat 40% OFF up to ₹100 on dining out\n\n"
                "Exclusive for Zomato Gold members. Dine out this weekend at handpicked partner restaurants and get flat 40% off. "
                "Use code GOLDDINING on pay via Zomato."
            ),
            "body_text": (
                "Zomato Gold Exclusive Deal\n\n"
                "Planning your weekend dinner?\n"
                "Enjoy Flat 40% OFF (up to ₹100) on your dining bill at over 1,500 partner restaurants.\n\n"
                "How to claim:\n"
                "1. Walk into any Gold partner restaurant\n"
                "2. Open Zomato > Dining Out > Pay Bill\n"
                "3. Apply coupon code: GOLDDINING\n\n"
                "Valid until Sunday midnight."
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 520px; margin: 0 auto; color: #1c1c1c;">
              <div style="background: #e23744; padding: 22px; color: white; text-align: center; border-radius: 8px 8px 0 0;">
                <h2 style="margin: 0; font-size: 26px; font-weight: 800; letter-spacing: -1px;">zomato gold</h2>
                <p style="margin: 6px 0 0; font-size: 14px;">Flat 40% OFF on Dining Out</p>
              </div>
              <div style="border: 1px solid #e8e8e8; border-top: none; padding: 22px; text-align: center; border-radius: 0 0 8px 8px; background: #fff;">
                <p style="font-size: 14px; color: #4f4f4f; margin: 0 0 16px;">Use code <strong>GOLDDINING</strong> when you pay via Zomato at partner cafes &amp; bistros.</p>
                <a href="#" style="background: #e23744; color: #fff; text-decoration: none; padding: 10px 22px; border-radius: 6px; font-weight: 600; font-size: 13.5px; display: inline-block;">Explore Restaurants</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_coursera_rec",
            "thread_id": "th_coursera_rec",
            "sender_name": "Coursera",
            "sender_email": "no-reply@coursera.org",
            "account": "abhed.student@bitmesra.ac.in",
            "subject": "New course recommended for you: Advanced System Design & Distributed Systems",
            "date_str": "Thu, 15 Oct 2026 12:10:00 +0530",
            "timestamp": now - 3600 * 84,
            "label": "low_priority",
            "confidence": 0.95,
            "unread": 0,
            "model_input": (
                "From: Coursera <no-reply@coursera.org>\n"
                "Subject: New course recommended: Advanced System Design & Distributed Systems\n\n"
                "Based on your interest in Computer Science and Cloud Computing, explore this 4-week specialization "
                "taught by Stanford engineering faculty. Financial aid available for verified university students."
            ),
            "body_text": (
                "Coursera Learning Digest for Abhed\n\n"
                "Recommended Course:\n"
                "Advanced System Design & Distributed Architecture\n"
                "Offered by Stanford Online\n\n"
                "Syllabus Highlights:\n"
                "• Raft and Paxos Consensus Protocols\n"
                "• LSM Trees, Write-Ahead Logging (WAL) and B-Trees\n"
                "• CAP Theorem in Real-world Storage Systems\n\n"
                "Enroll with your student email for verified course certification discount."
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; color: #1f1f1f;">
              <div style="padding: 16px 20px; border-bottom: 1px solid #e0e0e0;">
                <span style="font-size: 20px; font-weight: bold; color: #0056d2;">coursera</span>
              </div>
              <div style="padding: 22px;">
                <h3 style="font-size: 17px; margin: 0 0 10px; color: #0056d2;">Advanced System Design &amp; Distributed Systems</h3>
                <p style="font-size: 13.5px; color: #555; margin: 0 0 16px;">Offered by Stanford Online · 4 weeks · Intermediate level</p>
                <a href="#" style="background: #0056d2; color: #fff; text-decoration: none; padding: 9px 20px; border-radius: 4px; font-weight: 600; font-size: 13px; display: inline-block;">Learn More</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_github_sec_alert",
            "thread_id": "th_github_sec_alert",
            "sender_name": "GitHub Security",
            "sender_email": "security@github.com",
            "account": "abhed8604@gmail.com",
            "subject": "[Security Advisory] Critical vulnerability found in jinja2 dependency",
            "date_str": "Sun, 18 Oct 2026 23:10:00 +0530",
            "timestamp": now - 3600 * 2,
            "label": "very_important",
            "confidence": 0.97,
            "unread": 1,
            "model_input": (
                "From: GitHub Security <security@github.com>\n"
                "Subject: [Security Advisory] Critical vulnerability in jinja2\n\n"
                "Dependabot detected a critical severity security advisory in repository abhed8604/inboxzen. "
                "Advisory: Remote Code Execution via SSTI in Jinja2 < 3.1.5. Recommended action: upgrade jinja2 >= 3.1.5 immediately."
            ),
            "body_text": (
                "GitHub Dependabot Alert\n\n"
                "Repository: abhed8604/inboxzen\n"
                "Severity: Critical (CVSS 9.8)\n"
                "Package: jinja2 (Python)\n"
                "Vulnerable versions: < 3.1.5\n"
                "Patched version: 3.1.5\n\n"
                "Description:\n"
                "A server-side template injection vulnerability exists in Jinja2 where un-sanitized context parameters "
                "allow arbitrary Python code execution on host machines.\n\n"
                "Recommended fix:\n"
                "pip install --upgrade jinja2>=3.1.5\n\n"
                "View details and create pull request:\n"
                "https://github.com/abhed8604/inboxzen/security/dependabot/1"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 600px; margin: 0 auto; color: #24292f;">
              <div style="border: 1px solid #d0d7de; border-radius: 8px; overflow: hidden;">
                <div style="background: #ffebe9; border-bottom: 1px solid rgba(255, 129, 130, 0.4); padding: 14px 20px; display: flex; align-items: center;">
                  <span style="background: #cf222e; color: white; border-radius: 4px; padding: 3px 8px; font-size: 11px; font-weight: 700; margin-right: 12px; letter-spacing: 0.5px;">CRITICAL</span>
                  <span style="font-weight: 600; color: #cf222e; font-size: 14px;">Dependabot Security Advisory</span>
                </div>
                <div style="padding: 20px; background: #fff; color: #24292f;">
                  <h3 style="margin: 0 0 10px; font-size: 16px; color: #24292f;">Remote Code Execution in jinja2 &lt; 3.1.5</h3>
                  <p style="margin: 0 0 16px; color: #57606a; font-size: 13.5px;">Detected in <strong style="color: #24292f;">abhed8604/inboxzen</strong> (requirements.txt)</p>
                  <div style="background: #f6f8fa; border: 1px solid #d0d7de; border-radius: 6px; padding: 12px 16px; margin-bottom: 18px; font-size: 13px; color: #24292f;">
                    <div><strong>Package:</strong> <code style="color: #cf222e; background: #ffebe9; padding: 2px 4px; border-radius: 3px;">jinja2</code></div>
                    <div style="margin-top: 4px;"><strong>Remediation:</strong> Upgrade to <code style="color: #1a7f37; background: #dafbe1; padding: 2px 4px; border-radius: 3px;">jinja2 &gt;= 3.1.5</code></div>
                  </div>
                  <a href="#" style="background: #2da44e; color: #fff; text-decoration: none; padding: 8px 18px; border-radius: 6px; font-weight: 600; font-size: 13px; display: inline-block;">Open Automated PR</a>
                </div>
              </div>
            </div>
            """
        },
        {
            "id": "msg_hdfc_alert",
            "thread_id": "th_hdfc_alert",
            "sender_name": "HDFC Bank Alerts",
            "sender_email": "alerts@hdfcbank.net",
            "account": "abhed8604@gmail.com",
            "subject": "Alert: INR 3,499.00 debited from A/c **4108 for AWS Web Services",
            "date_str": "Sun, 18 Oct 2026 21:05:00 +0530",
            "timestamp": now - 3600 * 4,
            "label": "very_important",
            "confidence": 0.99,
            "unread": 1,
            "model_input": (
                "From: HDFC Bank Alerts <alerts@hdfcbank.net>\n"
                "Subject: Alert: INR 3,499.00 debited from A/c **4108\n\n"
                "Dear Customer, INR 3,499.00 has been debited from your account **4108 on 18-OCT-26 via Auto-Debit "
                "towards AMAZON WEB SERVICES INC. Available balance: INR 48,210.45. Not you? Call 1800 258 3838 immediately."
            ),
            "body_text": (
                "HDFC Bank InstaAlert\n\n"
                "Transaction Notification\n"
                "Dear ABHED,\n\n"
                "INR 3,499.00 has been debited from your Account **4108 on 18-OCT-26 at 21:05:00.\n"
                "Merchant: AMAZON WEB SERVICES BILLING\n"
                "Payment Mode: International Standing Instruction (SI)\n"
                "Available Balance: INR 48,210.45\n\n"
                "If this transaction was not authorized by you, please block your card immediately:\n"
                "SMS BLOCK to 5676712 or call 1800 258 3838."
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 540px; margin: 0 auto; color: #1c1c1c; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
              <div style="background: #004c8f; padding: 18px 24px; color: white;">
                <h3 style="margin: 0; font-size: 18px; font-weight: 700; letter-spacing: -0.5px;">HDFC BANK</h3>
                <p style="margin: 3px 0 0; font-size: 12px; opacity: 0.9;">InstaAlert Debit Notification</p>
              </div>
              <div style="padding: 24px; background: #fff;">
                <p style="font-size: 14px; margin-top: 0;">Dear <strong>ABHED</strong>,</p>
                <div style="background: #f4f7fb; border-left: 4px solid #004c8f; padding: 16px; margin: 18px 0; border-radius: 0 6px 6px 0;">
                  <div style="font-size: 20px; font-weight: 700; color: #d93025; margin-bottom: 8px;">₹ 3,499.00 <span style="font-size: 13px; font-weight: normal; color: #555;">Debited</span></div>
                  <div style="font-size: 13px; color: #444; line-height: 1.5;">
                    <div><strong>A/c Number:</strong> **4108</div>
                    <div><strong>Merchant:</strong> Amazon Web Services Inc.</div>
                    <div><strong>Date &amp; Time:</strong> 18-OCT-2026 21:05:00 IST</div>
                    <div><strong>Available Balance:</strong> ₹ 48,210.45</div>
                  </div>
                </div>
                <p style="font-size: 12px; color: #666; margin-bottom: 0;">If you did not authorize this transaction, please call 1800 258 3838 immediately.</p>
              </div>
            </div>
            """
        },
        {
            "id": "msg_bit_exam_schedule",
            "thread_id": "th_bit_exam_schedule",
            "sender_name": "Dean Academic Affairs · BIT Mesra",
            "sender_email": "dean.ap@bitmesra.ac.in",
            "account": "abhed.student@bitmesra.ac.in",
            "subject": "Notification: End Semester Examination Schedule (MO 2026)",
            "date_str": "Sun, 18 Oct 2026 18:45:00 +0530",
            "timestamp": now - 3600 * 6,
            "label": "very_important",
            "confidence": 0.98,
            "unread": 1,
            "model_input": (
                "From: Dean Academic Affairs <dean.ap@bitmesra.ac.in>\n"
                "Subject: Notification: End Semester Examination Schedule (MO 2026)\n\n"
                "The End Semester Examinations for 7th Semester B.Tech (2022-2026 batch) will commence from November 16, 2026. "
                "Admit cards will be available on ERP portal from Nov 5. Check department notice board for practical exam dates."
            ),
            "body_text": (
                "BIRLA INSTITUTE OF TECHNOLOGY, MESRA, RANCHI\n"
                "OFFICE OF THE DEAN OF ACADEMIC PROGRAMMES\n\n"
                "Notification No: DOAP/MO26/712\n"
                "Date: October 18, 2026\n\n"
                "Subject: Schedule for End Semester Examinations (Autumn / MO 2026)\n\n"
                "It is hereby notified to all 7th Semester B.Tech undergraduate students that theory end semester examinations "
                "will be conducted between 16 November 2026 and 28 November 2026.\n\n"
                "Key Deadlines:\n"
                "1. Submission of Minor Project & Seminar Reports: 08 November 2026\n"
                "2. Clearance of pending Institute/Hostel dues: 03 November 2026\n"
                "3. ERP Admit Card Download Window: 05 - 12 November 2026\n\n"
                "Dean (Academic Programmes)\n"
                "BIT Mesra, Ranchi"
            ),
            "body_html": """
            <div style="font-family: Georgia, serif; max-width: 600px; margin: 0 auto; color: #111; padding: 26px; border: 1px solid #dcdcdc; background: #fff;">
              <div style="text-align: center; border-bottom: 2px solid #002147; padding-bottom: 14px; margin-bottom: 18px;">
                <h2 style="margin: 0; color: #002147; font-size: 20px;">Birla Institute of Technology, Mesra</h2>
                <p style="margin: 4px 0 0; color: #555; font-size: 13px;">Office of the Dean (Academic Programmes)</p>
              </div>
              <h3 style="font-size: 16px; color: #002147; margin: 16px 0 8px;">Notice: End Semester Examinations - Autumn 2026</h3>
              <p style="font-size: 14px; line-height: 1.6;">Theory examinations for 7th Semester B.Tech students commence on <strong>16 November 2026</strong>. Admit cards must be downloaded from the student portal prior to November 12.</p>
              <div style="background: #f7f9fc; border: 1px solid #e1e7f0; border-radius: 6px; padding: 14px 18px; margin: 18px 0; font-size: 13.5px;">
                <div>• <strong>Major Project Interim Defense:</strong> Nov 06 - Nov 09</div>
                <div>• <strong>Theory Exams Period:</strong> Nov 16 - Nov 28</div>
                <div>• <strong>Admit Card Release:</strong> Nov 05 on ERP Portal</div>
              </div>
              <p style="font-size: 13px; color: #666; margin-top: 22px;">Prof. R. N. Mukherjee<br/>Dean of Academic Programmes</p>
            </div>
            """
        },
        {
            "id": "msg_sentry_issue",
            "thread_id": "th_sentry_issue",
            "sender_name": "Sentry Alert",
            "sender_email": "alerts@sentry.io",
            "account": "abhed.work@inboxzen.dev",
            "subject": "Issue #409: DatabaseLockedError in BackgroundWorkerService",
            "date_str": "Sun, 18 Oct 2026 17:15:00 +0530",
            "timestamp": now - 3600 * 7,
            "label": "very_important",
            "confidence": 0.96,
            "unread": 1,
            "model_input": (
                "From: Sentry <alerts@sentry.io>\n"
                "Subject: Issue #409: DatabaseLockedError in BackgroundWorkerService\n\n"
                "New issue in inboxzen-backend (production). sqlite3.OperationalError: database is locked. "
                "Triggered 14 times in last 5 minutes on host worker-01. Immediate investigation required."
            ),
            "body_text": (
                "Sentry Alert: New Issue Detected\n\n"
                "Project: inboxzen-backend\n"
                "Environment: production\n"
                "Issue ID: INBOX-409\n"
                "Title: sqlite3.OperationalError: database is locked\n"
                "Culprit: app.gmail_sync in background_classify_loop\n"
                "Event Count: 14 events across 3 user threads in 5m\n\n"
                "Stacktrace:\n"
                "  File \"app/gmail_sync.py\", line 135, in background_classify_loop\n"
                "    conn.execute(\"UPDATE emails SET label = ? WHERE id = ?\", (lbl, eid))\n"
                "sqlite3.OperationalError: database is locked\n\n"
                "View on Sentry:\n"
                "https://sentry.io/organizations/inboxzen/issues/409/"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 580px; margin: 0 auto; color: #2d2d38;">
              <div style="border: 1px solid #e1e3e8; border-radius: 8px; overflow: hidden;">
                <div style="background: #e1567c; padding: 12px 18px; color: white; display: flex; align-items: center; justify-content: space-between;">
                  <span style="font-weight: 700; font-size: 14px;">Sentry Issue Alert</span>
                  <span style="background: rgba(0,0,0,0.2); padding: 2px 8px; border-radius: 4px; font-size: 11px;">14 events / 5m</span>
                </div>
                <div style="padding: 20px; background: #fff;">
                  <h3 style="margin: 0 0 8px; font-size: 16px; color: #d0021b;">sqlite3.OperationalError: database is locked</h3>
                  <p style="margin: 0 0 14px; font-size: 13px; color: #6e707e;">Culprit: <code>app.gmail_sync.background_classify_loop</code> in production</p>
                  <div style="background: #181a1f; color: #e6e6e6; padding: 12px 14px; border-radius: 6px; font-family: monospace; font-size: 12px; margin-bottom: 16px;">
                    OperationalError: database is locked<br/>
                    &nbsp;&nbsp;File "app/gmail_sync.py", line 135, in sync_loop
                  </div>
                  <a href="#" style="background: #5846f6; color: white; text-decoration: none; padding: 8px 18px; border-radius: 6px; font-size: 13px; font-weight: 600; display: inline-block;">Resolve in Sentry</a>
                </div>
              </div>
            </div>
            """
        },
        {
            "id": "msg_figma_comment",
            "thread_id": "th_figma_comment",
            "sender_name": "Figma Notifications",
            "sender_email": "notifications@figma.com",
            "account": "abhed.work@inboxzen.dev",
            "subject": "Sarah Lin replied to your thread in 'InboxZen Design System v3'",
            "date_str": "Sun, 18 Oct 2026 14:20:00 +0530",
            "timestamp": now - 3600 * 10,
            "label": "important",
            "confidence": 0.93,
            "unread": 1,
            "model_input": (
                "From: Figma Notifications <notifications@figma.com>\n"
                "Subject: Sarah Lin replied in 'InboxZen Design System v3'\n\n"
                "Sarah Lin: 'Hey Abhed, I updated the token colors for the dark mode settings modal and the unread indicator pulse. "
                "Take a look at the prototype frame #4 when you get a chance!'"
            ),
            "body_text": (
                "Figma Comment Notification\n\n"
                "File: InboxZen Design System v3\n"
                "Page: Settings Modal & In-App Reader (Dark Mode)\n\n"
                "Sarah Lin replied:\n"
                "\"Hey Abhed, I updated the token colors for the dark mode settings modal and the unread indicator pulse. "
                "Take a look at the prototype frame #4 when you get a chance!\"\n\n"
                "Reply directly in Figma:\n"
                "https://www.figma.com/file/ibx992/InboxZen?node-id=402"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 540px; margin: 0 auto; color: #333; border: 1px solid #e5e5e5; border-radius: 8px; overflow: hidden; background: #fff;">
              <div style="padding: 16px 20px; border-bottom: 1px solid #f0f0f0; display: flex; align-items: center; gap: 10px;">
                <span style="font-size: 18px; font-weight: 700; color: #000;">Figma</span>
                <span style="color: #888; font-size: 13px;">· InboxZen Design System v3</span>
              </div>
              <div style="padding: 20px;">
                <div style="display: flex; gap: 12px; margin-bottom: 14px;">
                  <div style="width: 32px; height: 32px; border-radius: 50%; background: #0c8ce9; color: white; display: flex; align-items: center; justify-content: center; font-weight: bold; font-size: 13px;">SL</div>
                  <div>
                    <div style="font-size: 14px; font-weight: 600;">Sarah Lin</div>
                    <div style="font-size: 12px; color: #888;">Product Designer</div>
                  </div>
                </div>
                <p style="font-size: 14px; line-height: 1.5; color: #222; background: #f7f7f7; padding: 14px; border-radius: 6px; margin: 0 0 16px;">
                  "Hey Abhed, I updated the token colors for the dark mode settings modal and the unread indicator pulse. Take a look at prototype frame #4 when you get a chance!"
                </p>
                <a href="#" style="background: #0c8ce9; color: white; text-decoration: none; padding: 9px 18px; border-radius: 6px; font-size: 13px; font-weight: 600; display: inline-block;">Open in Figma</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_hackathon_confirmed",
            "thread_id": "th_hackathon_confirmed",
            "sender_name": "Devfolio Community",
            "sender_email": "notifications@devfolio.co",
            "account": "abhed8604@gmail.com",
            "subject": "Application Accepted: HackNITR 6.0 Hackathon - In-Person Track",
            "date_str": "Sun, 18 Oct 2026 10:30:00 +0530",
            "timestamp": now - 3600 * 14,
            "label": "important",
            "confidence": 0.95,
            "unread": 1,
            "model_input": (
                "From: Devfolio <notifications@devfolio.co>\n"
                "Subject: Application Accepted: HackNITR 6.0 Hackathon\n\n"
                "Congratulations Team Zen! Your project proposal for HackNITR 6.0 has been accepted. "
                "Confirm your team RSVP by October 24 to claim hacker pass, swags, and accommodation at NIT Rourkela."
            ),
            "body_text": (
                "Devfolio · HackNITR 6.0\n\n"
                "You're in! Congratulations Abhed!\n\n"
                "Your application for HackNITR 6.0 (Offline Track at NIT Rourkela) has been ACCEPTED by the organizing committee.\n\n"
                "Next Steps:\n"
                "1. RSVP on Devfolio dashboard before October 24, 2026 23:59 IST\n"
                "2. Join the official Discord server to coordinate with mentors and teammates\n"
                "3. Check the travel advisory and hostel accommodation checklist\n\n"
                "View your hacker dashboard:\n"
                "https://devfolio.co/hacknitr6/dashboard"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; color: #222; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden;">
              <div style="background: #3770ff; padding: 22px; color: white; text-align: center;">
                <h2 style="margin: 0; font-size: 22px;">🎉 You're in for HackNITR 6.0!</h2>
                <p style="margin: 6px 0 0; opacity: 0.9; font-size: 13.5px;">NIT Rourkela · 36-hour National Hackathon</p>
              </div>
              <div style="padding: 24px; background: #fff;">
                <p style="font-size: 14.5px; margin-top: 0;">Hey <strong>Abhed</strong>,</p>
                <p style="font-size: 14px; line-height: 1.5; color: #444;">We reviewed over 3,000 hacker applications and your team proposal stood out. We are excited to welcome you to the offline hackathon!</p>
                <div style="background: #f0f4ff; border-left: 4px solid #3770ff; padding: 14px 16px; margin: 18px 0; border-radius: 0 6px 6px 0; font-size: 13.5px;">
                  <strong>Action Required:</strong> Confirm your RSVP on Devfolio before <strong>Oct 24</strong> to secure hostel lodging.
                </div>
                <a href="#" style="background: #3770ff; color: #fff; text-decoration: none; padding: 10px 22px; border-radius: 6px; font-weight: 600; font-size: 13.5px; display: inline-block;">Confirm RSVP</a>
              </div>
            </div>
            """
        },
        {
            "id": "msg_uber_receipt",
            "thread_id": "th_uber_receipt",
            "sender_name": "Uber Receipts",
            "sender_email": "uber.india@uber.com",
            "account": "abhed8604@gmail.com",
            "subject": "Your Sunday evening trip with Uber: ₹214.50",
            "date_str": "Sun, 18 Oct 2026 06:40:00 +0530",
            "timestamp": now - 3600 * 18,
            "label": "low_priority",
            "confidence": 0.98,
            "unread": 1,
            "model_input": (
                "From: Uber Receipts <uber.india@uber.com>\n"
                "Subject: Your Sunday evening trip with Uber: ₹214.50\n\n"
                "Total ₹214.50 paid via Uber Auto. Ride from BIT Mesra Main Gate to Nucleus Mall, Ranchi. "
                "Driver: Rajesh Kumar (4.91 rating). Thank you for riding with Uber."
            ),
            "body_text": (
                "Uber Receipt\n\n"
                "Total: ₹214.50\n"
                "Date: Sunday, October 18, 2026\n"
                "Trip: BIT Mesra Campus Gate -> Nucleus Mall, Circular Road, Ranchi\n"
                "Payment Method: Amazon Pay UPI\n"
                "Driver: Rajesh Kumar (4.91 ★)\n\n"
                "Distance: 14.2 km · Duration: 28 min\n\n"
                "For ride support or lost items, visit help.uber.com"
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 500px; margin: 0 auto; color: #000; border: 1px solid #e5e5e5; border-radius: 8px; overflow: hidden; background: #fff;">
              <div style="background: #000; padding: 20px 24px; color: white; display: flex; justify-content: space-between; align-items: center;">
                <span style="font-size: 22px; font-weight: 600;">Uber</span>
                <span style="font-size: 18px; font-weight: 600;">₹ 214.50</span>
              </div>
              <div style="padding: 22px;">
                <div style="font-size: 13.5px; color: #555; margin-bottom: 16px;">Sunday, Oct 18, 2026 · Uber Auto</div>
                <div style="border-top: 1px solid #eee; border-bottom: 1px solid #eee; padding: 14px 0; font-size: 13px; line-height: 1.6;">
                  <div><strong>Pickup:</strong> BIT Mesra Main Gate, Ranchi</div>
                  <div><strong>Drop:</strong> Nucleus Mall, Circular Road, Ranchi</div>
                  <div style="color: #666; margin-top: 4px;">Paid via UPI · 14.2 km</div>
                </div>
                <p style="font-size: 12px; color: #888; margin: 16px 0 0;">Thanks for riding with us.</p>
              </div>
            </div>
            """
        },
        {
            "id": "msg_tldr_ai",
            "thread_id": "th_tldr_ai",
            "sender_name": "TLDR AI",
            "sender_email": "dan@tldrnewsletter.com",
            "account": "abhed8604@gmail.com",
            "subject": "TLDR AI: Claude 3.7 Sonnet benchmarks & local quantized reasoning models",
            "date_str": "Sat, 17 Oct 2026 23:50:00 +0530",
            "timestamp": now - 3600 * 22,
            "label": "low_priority",
            "confidence": 0.97,
            "unread": 1,
            "model_input": (
                "From: TLDR AI <dan@tldrnewsletter.com>\n"
                "Subject: TLDR AI: Claude 3.7 Sonnet & local reasoning models\n\n"
                "Daily roundup for AI engineers. Anthropic publishes new evals on tool use and agent loops; "
                "llama.cpp adds accelerated flash-attention kernels for Turing architecture (GTX 1650/1660); "
                "DeepSeek releases open-weights MoE weights."
            ),
            "body_text": (
                "TLDR AI Daily Digest\n\n"
                "HEADLINES & RESEARCH:\n\n"
                "1. Anthropic Claude 3.7 Technical Report\n"
                "Detailed evaluation of autonomous multi-step reasoning capabilities, highlighting 94.2% on SWE-bench verified.\n\n"
                "2. llama.cpp Optimizations for Legacy NVIDIA Turing GPUs\n"
                "New Q4_K_M and Q8_0 execution kernels deliver 2.1x faster prompt processing on GTX 1650 with zero VRAM overhead.\n\n"
                "3. vLLM Distributed Serving Updates\n"
                "Support for speculative sampling and dynamic draft model batching in microservice deployments."
            ),
            "body_html": """
            <div style="font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif; max-width: 560px; margin: 0 auto; color: #1a1a1a; border: 1px solid #e0e0e0; border-radius: 8px; overflow: hidden; background: #fff;">
              <div style="background: #111; padding: 18px 24px; color: white;">
                <span style="font-size: 20px; font-weight: 800; letter-spacing: -0.5px; color: #50e3c2;">TLDR</span>
                <span style="font-size: 14px; margin-left: 8px; opacity: 0.8;">AI &amp; Machine Learning Digest</span>
              </div>
              <div style="padding: 22px;">
                <h4 style="margin: 0 0 6px; font-size: 15px; color: #000;">1. Anthropic releases new agentic reasoning evals</h4>
                <p style="font-size: 13.5px; color: #555; line-height: 1.5; margin: 0 0 16px;">Comprehensive benchmarks on SWE-bench verified show strong leaps in multi-tool agent execution.</p>
                <h4 style="margin: 0 0 6px; font-size: 15px; color: #000;">2. llama.cpp adds fast CUDA kernels for Turing cards</h4>
                <p style="font-size: 13.5px; color: #555; line-height: 1.5; margin: 0 0 16px;">GTX 1650 and GTX 1660 GPUs now achieve up to 38 tokens/second on Q8_0 quantized models.</p>
              </div>
            </div>
            """
        }
    ]

    with get_db() as conn:
        conn.execute("DELETE FROM emails")
        for d in demo_data:
            conn.execute("""
                INSERT INTO emails (
                    id, thread_id, sender_name, sender_email, subject,
                    date_str, timestamp, model_input, body_text, body_html,
                    label, confidence, prompt_hash, unread, account
                ) VALUES (
                    ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?
                )
            """, (
                d["id"], d["thread_id"], d["sender_name"], d["sender_email"], d["subject"],
                d["date_str"], d["timestamp"], d["model_input"], d["body_text"], d["body_html"],
                d["label"], d["confidence"], prompt_hash, d["unread"], d["account"]
            ))

    print(f"Successfully seeded {len(demo_data)} emails across 3 accounts.")

if __name__ == "__main__":
    seed_demo_emails()
