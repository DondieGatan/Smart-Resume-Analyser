# Running the app on Hugging Face Spaces

Spaces keep a Docker app running without the 15-minute sleep of Render's free plan (a Space only
pauses after about two days with no visitors) and give it far more memory (16 GB instead of 512 MB).

1. Sign in at huggingface.co and create a Space: **New Space**, SDK **Docker**, template **Blank**, visibility **Public**.
2. In the Space, open **Settings > Variables and secrets** and add the app's settings. Use **Secrets** for keys and the database URL:

   | Name | Value |
   |---|---|
   | `DATABASE_URL` (secret) | the Neon direct connection string (no `-pooler` in the host) |
   | `DB_SCHEMA` | `resume_analyser` |
   | `SECRET_KEY` (secret) | a long random string |
   | `SENDGRID_API_KEY` (secret), `SENDGRID_FROM` | for verification and reset emails |
   | `GEMINI_API_KEY` (secret), `GEMINI_MODEL` | for the resume-builder assistant (`gemini-2.5-flash`) |

3. Create an access token with **write** access at huggingface.co/settings/tokens.
4. From the repo root run, and enter your Hugging Face username and the token as the password when asked:

   ```bash
   HF_SPACE=<your-username>/<space-name> bash deploy/huggingface/deploy.sh
   ```

5. Watch the build on the Space page (the first one takes a few minutes: it installs the model).
   The app is at `https://<your-username>-<space-name>.hf.space`. Open that address directly rather
   than the Space page, because the sign-in cookie does not work inside the page's embedded frame.

Re-run step 4 after each change you want to publish; it always publishes the latest commit.
