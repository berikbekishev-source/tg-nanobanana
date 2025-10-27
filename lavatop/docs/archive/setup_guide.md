# Lava.top Setup Guide

## Step 1: Lava.top Account Setup

### Create Account
1. Go to [Lava.top](https://lava.top)
2. Register business account
3. Complete verification

### Create Products
For each token package, create a product:

#### 100 Tokens Product
- **Name**: 100 Tokens
- **Price**: $5.00
- **Currency**: USD
- **Type**: One-time payment

#### Future Products (when ready)
- 200 Tokens - $10
- 500 Tokens - $25
- 1000 Tokens - $50

### Get API Credentials
1. Go to Settings → API
2. Generate API Key
3. Copy Webhook Secret

### Configure Webhook
1. Go to Webhooks settings
2. Add webhook URL: `https://your-app.railway.app/api/miniapp/lava-webhook`
3. Select events: Payment Success, Payment Failed
4. Save webhook secret

## Step 2: Project Configuration

### Environment Variables

#### Local Development (.env)
```bash
LAVA_API_KEY=your_api_key_here
LAVA_WEBHOOK_SECRET=your_webhook_secret_here
PUBLIC_BASE_URL=http://localhost:8000
```

#### Railway Production
```bash
railway variables --set "LAVA_API_KEY=your_api_key_here" --service web
railway variables --set "LAVA_WEBHOOK_SECRET=your_webhook_secret" --service web
```

### Update Payment Links
Edit `lavatop/provider.py`:

```python
PAYMENT_LINKS = {
    100: "https://app.lava.top/products/YOUR_PRODUCT_ID/YOUR_OFFER_ID",
    # Add more as products are created
}
```

## Step 3: Integration Setup

### Import Module
```python
# In your Django app
from lavatop import get_payment_url, process_webhook
```

### Update API Endpoint
```python
# miniapp/api.py
from lavatop import get_payment_url

@miniapp_api.post("/create-payment")
def create_payment(request, data):
    # Get payment URL
    payment_url = get_payment_url(
        credits=data.credits,
        transaction_id=transaction.id,
        user_email=data.email
    )

    return {"payment_url": payment_url}
```

### Update Webhook Handler
```python
# miniapp/api.py
from lavatop import process_webhook

@miniapp_api.post("/lava-webhook")
def lava_webhook(request):
    # Process webhook
    result = process_webhook(
        payload=request.body,
        signature=request.headers.get('X-Signature')
    )

    if result['action'] == 'credit_tokens':
        # Credit tokens to user
        user_balance.balance += result['tokens']
        user_balance.save()

    return {"ok": True}
```

## Step 4: Testing

### Local Testing
```bash
# Run test suite
python lavatop/tests/test_integration.py

# Test payment creation
python manage.py shell
>>> from lavatop import get_payment_url
>>> url = get_payment_url(100, "test_123", "test@email.com")
>>> print(url)
```

### Webhook Testing
Use ngrok for local webhook testing:
```bash
ngrok http 8000
# Update Lava.top webhook to ngrok URL
```

## Step 5: Production Deployment

### Pre-deployment Checklist
- [ ] API key configured in Railway
- [ ] Webhook secret configured
- [ ] Product created in Lava.top
- [ ] Payment links updated
- [ ] Tests passing

### Deploy
```bash
git add -A
git commit -m "Configure Lava.top payments"
git push
```

### Post-deployment
1. Test payment with small amount
2. Verify webhook received
3. Check token crediting
4. Monitor logs

## Step 6: Monitoring

### Check Logs
```bash
# Railway logs
railway logs --service web

# Django logs
tail -f logs/payment.log
```

### Common Log Entries
```
INFO: Payment created via SDK: payment_123
INFO: Using static link for 100 tokens
INFO: Processing Lava webhook: order_456
INFO: Payment order_456 completed
```

## Troubleshooting

### API Not Working
1. Verify API key is correct
2. Check network connectivity
3. Static links will be used as fallback

### Webhook Issues
1. Verify webhook URL in Lava.top
2. Check signature secret matches
3. Test with webhook testing tool

### Payment Not Credited
1. Check transaction exists
2. Verify webhook processed
3. Review token calculation logic

## Support Contacts

### Lava.top Support
- Email: support@lava.top
- Documentation: https://docs.lava.top

### Internal Support
- Check application logs
- Review this documentation
- Contact development team