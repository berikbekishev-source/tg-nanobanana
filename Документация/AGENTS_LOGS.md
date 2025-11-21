## 1. Deployments (Latest First)

| Status | Commit | Description | Date |
| :--- | :--- | :--- | :--- |
| ✅ STAGING | `7c51e41` | **Fix Remix Media Group (Unified Buffer)**: Implemented universal Redis buffer to collect all remix images (single or album) for 1.0s. Uses Lua script for atomic fetching. Fixes race conditions and double responses. | 2025-11-21 |
| ✅ STAGING | `a0e2b4c` | **Fix Remix Media Group (Robust)**: Added Lua script for atomic Redis operations to handle media groups correctly. Enhanced `pending_caption` logic to capture caption from any photo in the group. Fixed `min_needed` to 2. | 2025-11-21 |
| ✅ STAGING | `5655735` | **Fix Remix Media Group**: Added support for collecting photos from `media_group_id`. Auto-start generation when `min_needed` (2) photos + caption are received. Fixed issue where bot ignored multiple photos. | 2025-11-21 |
