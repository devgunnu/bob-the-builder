---
source_url: https://docs.firecrawl.dev/webhooks/testing
title: Webhook Testing | Firecrawl
fetched_at: 2026-10-31T02:32:44+00:00
---

Verify that your webhook integration works before deploying to production. This page covers how to receive webhooks on your local machine and how to diagnose common delivery and verification failures.

## Local Development

Webhooks require a publicly reachable URL, so you need to expose your local server to the internet during development.

### Using Cloudflare Tunnels

[Cloudflare Tunnels](https://github.com/cloudflare/cloudflared/releases) provide a free way to expose your local server without opening firewall ports:

```
cloudflared tunnel --url localhost:3000
```

You’ll get a public URL like `https://abc123.trycloudflare.com`. Use this in your webhook config:

```
{
  "url": "https://abc123.trycloudflare.com/webhook"
}
```

## Troubleshooting

### Webhooks Not Arriving

- **Endpoint not accessible** \- Verify your server is publicly reachable and firewalls allow incoming connections
- **Using HTTP** \- Webhook URLs must use HTTPS
- **Wrong events** \- Check the `events` filter in your webhook config
- **Timeout errors** \- Ensure your endpoint responds within 10 seconds

### Signature Verification Failing

The most common cause is using the parsed JSON body instead of the raw request body. A second cause is using the wrong secret, so confirm yours matches the value in your [account settings](https://www.firecrawl.dev/app/settings?tab=advanced).

```
// Wrong - using parsed body
const signature = crypto
  .createHmac('sha256', secret)
  .update(JSON.stringify(req.body))
  .digest('hex');

// Correct - using raw body
app.use('/webhook', express.raw({ type: 'application/json' }));
app.post('/webhook', (req, res) => {
  const signature = crypto
    .createHmac('sha256', secret)
    .update(req.body) // Raw buffer
    .digest('hex');
});
```
