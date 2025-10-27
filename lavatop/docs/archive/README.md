# Lava.top Payment Integration

## Overview
Complete payment system integration with Lava.top for processing token purchases in the Telegram bot.

## Features
- 🚀 Official SDK integration with automatic fallback
- 💳 Support for multiple token packages
- 🔒 Secure webhook processing with signature verification
- 📊 Comprehensive logging and error handling
- ⚡ Production-ready with staging support

## Quick Start

### Installation
```python
# The module is already part of the project
from lavatop import get_payment_url, process_webhook
```

### Basic Usage

#### Create Payment
```python
from lavatop import get_payment_url

# Generate payment URL for 100 tokens
payment_url = get_payment_url(
    credits=100,
    transaction_id="unique_transaction_id",
    user_email="customer@example.com"
)
```

#### Process Webhook
```python
from lavatop import process_webhook

# Handle incoming webhook
result = process_webhook(
    payload=webhook_data,
    signature=request.headers.get('X-Signature')
)

if result['success']:
    if result['action'] == 'credit_tokens':
        # Add tokens to user balance
        tokens = result['tokens']
```

## Current Status

### Supported Packages
| Tokens | Price | Status |
|--------|-------|--------|
| 100    | $5    | ✅ Active |
| 200    | $10   | 🔜 Coming Soon |
| 500    | $25   | 🔜 Coming Soon |
| 1000   | $50   | 🔜 Coming Soon |

### Payment Flow
1. User selects token package
2. System generates payment URL (SDK or static)
3. User completes payment on Lava.top
4. Webhook received and verified
5. Tokens credited to user balance
6. User notified in Telegram

## Configuration

### Environment Variables
```bash
LAVA_API_KEY=your_api_key_here
LAVA_WEBHOOK_SECRET=your_webhook_secret
PUBLIC_BASE_URL=https://your-domain.com
```

### Django Settings
```python
# config/settings.py
LAVA_API_KEY = os.getenv("LAVA_API_KEY")
LAVA_WEBHOOK_SECRET = os.getenv("LAVA_WEBHOOK_SECRET")
```

## Testing
```bash
# Run integration tests
python lavatop/tests/test_integration.py
```

## Architecture

### Module Structure
```
lavatop/
├── __init__.py       # Module exports
├── provider.py       # Main payment provider
├── webhook.py        # Webhook processing
├── tests/           # Test suite
├── docs/            # Documentation
└── config/          # Configuration files
```

### Key Components

#### Provider
- Manages SDK client initialization
- Handles payment creation
- Implements fallback logic

#### Webhook
- Verifies signatures
- Processes payment notifications
- Returns standardized responses

## Deployment

### Railway Setup
1. Add environment variables
2. Deploy code
3. Webhook URL: `https://your-app.railway.app/api/miniapp/lava-webhook`

### Production Checklist
- ✅ Environment variables configured
- ✅ Webhook URL registered in Lava.top
- ✅ Product created for 100 tokens
- ✅ Signature verification enabled
- ✅ Error logging configured

## Troubleshooting

### Common Issues

#### SDK Not Working
- Check API key is correct
- Verify product exists in Lava.top
- System will fall back to static links

#### Webhook Not Receiving
- Verify webhook URL in Lava.top
- Check signature secret matches
- Review server logs

#### Payment Not Processing
- Ensure transaction exists in database
- Check user balance updates
- Verify token calculation (20 tokens per dollar)

## Support
For issues or questions, check the logs or contact the development team.