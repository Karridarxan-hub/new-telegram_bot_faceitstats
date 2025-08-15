# Detailed Bug Report

**Report Date:** August 14, 2025  
**Tested Version:** Simple Bot (simple_bot.py)  
**Test Account:** Geun-Hee  
**Environment:** Development

## Critical Bugs

### 🔴 BUG #1: Undefined Variable Error in Map Statistics

**Severity:** HIGH  
**Priority:** IMMEDIATE  
**File:** `simple_bot.py`  
**Line:** 824  

**Description:**
The `stats_maps` callback handler references an undefined variable `map_text` causing a NameError when users click the "🗺️ Карты" button.

**Code Location:**
```python
@router.callback_query(F.data == "stats_maps")
async def callback_stats_maps(callback: CallbackQuery):
    # ... other code ...
    maps_text = map_text  # ← BUG: map_text is not defined
```

**Expected Behavior:**
Should generate map-specific statistics using the `format_map_specific_progress()` function.

**Actual Behavior:**
Will throw `NameError: name 'map_text' is not defined`

**Reproduction Steps:**
1. Start bot
2. Send /start command
3. Click "📊 Моя статистика"
4. Click "🗺️ Карты"
5. Bot crashes with NameError

**Fix Required:**
Replace line 824 with:
```python
maps_text = format_map_specific_progress(stats)
```

---

### 🔴 BUG #2: K/R Ratio Always Shows Zero

**Severity:** HIGH  
**Priority:** HIGH  
**File:** `utils/cs2_advanced_formatter.py`  
**Line:** 27  

**Description:**
The K/R (Kill/Round) ratio always displays as 0 in advanced statistics, making KAST% and other calculations inaccurate.

**Code Location:**
```python
kr_ratio = float(lifetime.get('Average K/R Ratio', '0'))  # Always returns '0'
```

**Expected Behavior:**
Should show actual kills per round ratio (e.g., 0.75)

**Actual Behavior:**
Always shows 0, affecting:
- KAST% calculation
- Entry frag estimation
- Role recommendations

**Investigation:**
FACEIT API may use different field name for K/R ratio, or calculation may be needed from other fields.

**Test Data:**
- Geun-Hee account shows K/R as 0
- Should calculate from total kills/total rounds or use different API field

**Fix Required:**
1. Investigate FACEIT API response structure for K/R data
2. Implement proper calculation if field is missing
3. Update formatter to use correct field name

---

### 🔴 BUG #3: Recent Form K/D Calculation Error

**Severity:** HIGH  
**Priority:** HIGH  
**File:** `utils/cs2_advanced_formatter.py`  
**Line:** 132  

**Description:**
Recent form K/D shows extremely high value (231.74) instead of realistic K/D ratio.

**Code Location:**
```python
recent_kd = float(recent.get('K/D Ratio', '0'))  # Returns incorrect value
```

**Expected Behavior:**
Should show recent K/D ratio similar to overall average (e.g., 1.05-1.15)

**Actual Behavior:**
Shows 231.74, indicating data parsing error

**Test Data:**
- Overall K/D: 1.11 (correct)
- Recent K/D: 231.74 (incorrect)

**Root Cause:**
Likely accessing wrong field in segments data or misinterpreting API response structure.

**Fix Required:**
1. Debug segments data structure
2. Verify correct field name for recent K/D
3. Add data validation to catch unrealistic values

---

### 🟡 BUG #4: Player Skill Level Not Accessible

**Severity:** MEDIUM  
**Priority:** MEDIUM  
**File:** `utils/cs2_advanced_formatter.py`  
**Line:** 21-22  

**Description:**
Player skill level and ELO show as "N/A" instead of actual values (Level 9, ELO 1807).

**Code Location:**
```python
text += f"🏆 <b>Уровень:</b> {getattr(player, 'skill_level', 'N/A')} | "
text += f"<b>ELO:</b> {getattr(player, 'faceit_elo', 'N/A')}\n\n"
```

**Expected Behavior:**
Should show "🏆 Уровень: 9 | ELO: 1807"

**Actual Behavior:**
Shows "🏆 Уровень: N/A | ELO: N/A"

**Root Cause:**
Player object structure uses nested games data. Correct access:
```python
player.games['cs2'].skill_level
player.games['cs2'].faceit_elo
```

**Fix Required:**
Update to access nested game data properly.

---

## Minor Issues

### 🟡 ISSUE #5: Console Encoding Problems

**Severity:** LOW  
**Priority:** LOW  
**Impact:** Development only  

**Description:**
Unicode emojis cause encoding errors in Windows console output during testing.

**Affects:**
- Development testing
- Debug output
- Not user-facing

**Workaround:**
Use file output for testing instead of console print.

---

### 🟡 ISSUE #6: HLTV Rating May Be Underestimated

**Severity:** LOW  
**Priority:** LOW  
**File:** `utils/cs2_advanced_formatter.py`  
**Line:** 77-78  

**Description:**
HLTV 2.0 rating calculation shows 0.50 for a Level 9 player with 1.11 K/D, which seems low.

**Expected Behavior:**
Level 9 player should typically have HLTV rating > 1.0

**Investigation Needed:**
Review HLTV rating calculation formula and parameters.

---

## Verification Required

### 🔄 PENDING: Callback Button Testing

**Status:** Cannot test without running bot  
**Priority:** HIGH  

**Required Tests:**
1. All statistics subdivision buttons
2. Navigation flow between menus
3. Back button functionality
4. Error handling in callbacks

### 🔄 PENDING: Live Match Monitoring

**Status:** Requires active match  
**Priority:** MEDIUM  

**Required Tests:**
1. Live match detection
2. Match analysis functionality
3. URL parsing for match analysis

---

## Summary

**Critical Bugs:** 3  
**Medium Priority:** 1  
**Minor Issues:** 2  
**Pending Verification:** 2  

**Immediate Actions Required:**
1. Fix undefined `map_text` variable (Blocks basic functionality)
2. Correct K/R ratio calculation (Affects multiple features)
3. Fix recent form K/D parsing (Misleading statistics)

**Estimated Fix Time:** 2-4 hours for critical bugs

---

**Testing Notes:**
- All bugs were identified through code analysis and API testing
- Live bot testing still required for complete verification
- User experience may have additional issues not visible in code review