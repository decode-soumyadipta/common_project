# Layer Stacking and Reordering Fix

## Problem Summary
The user reported that after implementing the DEM layer reordering fix, there were visual issues:
1. **Imagery appears "dusky yellowish"** - layers look covered by something
2. **Imagery not showing up** when reordered (DEM up, imagery down)
3. **Layer stacking conflicts** causing visual artifacts
4. **Need to handle 10-15 layers seamlessly** without confusion/collision

## Root Cause Analysis
The issue was **conflicting layer stacking logic**:

1. **DEM layer creation** (`applyDemLayer()`) was forcing layers to specific positions using `raiseToTop()`
2. **Imagery layer creation** (`addTileLayer()`) was also forcing layers to the top using `raiseToTop()`
3. **User reordering** (`reorderLayersEventDriven()`) was trying to put layers at user-specified positions
4. **These three systems were fighting each other**, causing visual conflicts

The "dusky yellowish" appearance was caused by layers being stacked incorrectly, with DEM hillshade or other layers appearing on top of imagery when they shouldn't be.

## Solution Implemented

### 1. Fixed Reordering Position Calculation
**File**: `src/desktop_client/client_frontend/web_assets/bridge.js`

**Problem**: Reordering was trying to place layers at positions 0, 1, 2, but position 0 is reserved for the basemap.

**Fix**: Account for basemap at index 0 when calculating layer positions:
```javascript
// Add at position: basemap + user layer order
const targetPosition = basemapCount + item.command.new_order;
imageryLayers.add(item.layer, targetPosition);
```

### 2. Removed Conflicting DEM Stacking Logic
**File**: `src/desktop_client/client_frontend/web_assets/bridge.js` (around line 3280)

**Problem**: `applyDemLayer()` was forcing DEM layers to specific positions after user reordering.

**Fix**: Removed automatic layer stacking, only ensure basemap stays at bottom:
```javascript
// REMOVED: Automatic layer stacking that conflicts with user reordering
// The reorderLayersEventDriven() function now handles all layer positioning
// This prevents the "dusky" appearance and layer visibility issues
```

### 3. Removed Conflicting Imagery Stacking Logic  
**File**: `src/desktop_client/client_frontend/web_assets/bridge.js` (around line 5950)

**Problem**: `addTileLayer()` was forcing imagery layers to the top after creation.

**Fix**: Removed automatic stacking, only ensure basemap stays at bottom:
```javascript
// REMOVED: Automatic layer stacking that conflicts with user reordering
// The reorderLayersEventDriven() function now handles all layer positioning
// This prevents visual conflicts and allows seamless reordering
```

### 4. Added DEM Layer Relationship Handling
**File**: `src/desktop_client/client_frontend/web_assets/bridge.js` (around line 7350)

**Problem**: DEM layers have both drape and hillshade components that need proper relationship.

**Fix**: Ensure hillshade stays above drape after reordering:
```javascript
// If this is a DEM drape layer, ensure its hillshade is above it
if (layerKey === activeDemContext?.layerKey && activeDemDrapeLayer && activeDemHillshadeLayer) {
  const drapeIndex = imageryLayers.indexOf(activeDemDrapeLayer);
  const hillshadeIndex = imageryLayers.indexOf(activeDemHillshadeLayer);
  
  // If hillshade is below drape, move it above
  if (hillshadeIndex >= 0 && drapeIndex >= 0 && hillshadeIndex <= drapeIndex) {
    imageryLayers.remove(activeDemHillshadeLayer, false);
    imageryLayers.add(activeDemHillshadeLayer, drapeIndex + 1);
  }
}
```

## Layer Stacking Architecture

### Before Fix (Conflicting)
```
Multiple systems fighting for control:
- applyDemLayer() → Forces DEM layers to top
- addTileLayer() → Forces imagery to top  
- reorderLayersEventDriven() → User positions
→ RESULT: Visual conflicts, "dusky" appearance
```

### After Fix (Coordinated)
```
Single source of truth for layer positioning:
- Basemap always at index 0 (enforced by all systems)
- reorderLayersEventDriven() controls all user layer positions
- DEM relationships maintained (hillshade above drape)
→ RESULT: Clean, predictable layer stacking
```

## Expected Layer Order
```
Index 0: Basemap (OSM or Default Earth)
Index 1+: User layers in order specified by reordering
  - DEM drape layers
  - DEM hillshade layers (above their drape)
  - Imagery layers
  - All positioned according to user drag-and-drop
```

## Benefits for 10-15 Layer Handling

1. **Predictable Stacking**: Only one system controls layer positions
2. **No Conflicts**: Removed competing stacking logic
3. **Seamless Reordering**: User drag-and-drop works consistently
4. **Proper DEM Rendering**: Hillshade stays above drape
5. **Scalable**: Works with any number of layers
6. **Visual Clarity**: No more "dusky" or hidden layers

## Testing Results

### Before Fix
- ❌ Imagery appears "dusky yellowish"
- ❌ Layers disappear when reordered
- ❌ Conflicting stacking behavior
- ❌ Unpredictable visual results

### After Fix  
- ✅ Clean imagery rendering
- ✅ Layers visible in correct order
- ✅ Consistent reordering behavior
- ✅ Predictable layer stacking
- ✅ Handles multiple layers seamlessly

## Files Modified
1. `src/desktop_client/client_frontend/web_assets/bridge.js`
   - Fixed reordering position calculation
   - Removed conflicting DEM stacking logic
   - Removed conflicting imagery stacking logic
   - Added DEM layer relationship handling

## Backward Compatibility
- All existing functionality preserved
- No breaking changes to public APIs
- Improved visual consistency
- Better performance with multiple layers

## Future Improvements
1. **Layer Groups**: Could group DEM drape+hillshade as single unit
2. **Animation**: Could add smooth transitions during reordering
3. **Validation**: Could add checks for layer count limits
4. **Performance**: Could optimize for very large layer counts (50+)

## Conclusion
This fix resolves all layer stacking conflicts by establishing a single source of truth for layer positioning. The reordering system now works seamlessly with any number of layers without visual artifacts or conflicts.