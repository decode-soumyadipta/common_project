# DEM Layer Reordering Fix

## Problem Summary
The user reported that DEM layers were not reordering on the map when dragged in the search results table. The JavaScript console showed "EVENT_DRIVEN: Layer not found for reordering" errors for DEM layers.

## Root Cause Analysis
The issue was that DEM layers were handled differently from imagery layers in the JavaScript code:

1. **Imagery layers**: Created in `addTileLayer()` → get `_layerKey` property → added to `managedImageryLayers` map
2. **DEM layers**: Created in `addDemLayer()` → stored as `activeDemDrapeLayer` and `activeDemHillshadeLayer` → NO `_layerKey` property → NOT in `managedImageryLayers` map

The `reorderLayersEventDriven()` function only looks in `managedImageryLayers` and checks for `_layerKey`, so it couldn't find DEM layers.

## Solution Implemented
Modified the `applyDemLayer()` function in `bridge.js` to:

### 1. Add `_layerKey` property to DEM layers
- **DEM drape layer**: Gets `activeDemContext.layerKey` as its `_layerKey`
- **DEM hillshade layer**: Gets `activeDemContext.layerKey + ":hillshade"` as its `_layerKey`

### 2. Add DEM layers to `managedImageryLayers` map
- **DEM drape layer**: Added to map with key `activeDemContext.layerKey`
- **DEM hillshade layer**: Added to map with key `activeDemContext.layerKey + ":hillshade"`

### 3. Clean up map entries when DEM layers are removed
Added cleanup code in multiple locations:
- `clearDemTerrainMode()`: Remove both drape and hillshade from map
- `applyDemLayer()` drape removal: Remove old drape from map
- `applyDemLayer()` hillshade removal: Remove old hillshade from map

## Files Modified
- `src/desktop_client/client_frontend/web_assets/bridge.js`

## Changes Made

### 1. DEM Drape Layer Creation (around line 3050)
```javascript
// CRITICAL FIX: Tag DEM drape layer with key for reordering functionality
activeDemDrapeLayer._layerKey = activeDemContext.layerKey;
activeDemDrapeLayer._layerName = activeDemContext.name;

// CRITICAL FIX: Add DEM drape layer to managedImageryLayers for reordering
managedImageryLayers.set(activeDemContext.layerKey, activeDemDrapeLayer);
```

### 2. DEM Hillshade Layer Creation (around line 3220)
```javascript
// CRITICAL FIX: Tag DEM hillshade layer with key for reordering functionality
// Use a different key suffix to distinguish from drape layer
const hillshadeKey = activeDemContext.layerKey + ":hillshade";
activeDemHillshadeLayer._layerKey = hillshadeKey;
activeDemHillshadeLayer._layerName = activeDemContext.name + " (Hillshade)";

// CRITICAL FIX: Add DEM hillshade layer to managedImageryLayers for reordering
managedImageryLayers.set(hillshadeKey, activeDemHillshadeLayer);
```

### 3. Cleanup in clearDemTerrainMode() (around line 2196)
```javascript
// CRITICAL FIX: Remove DEM drape layer from managedImageryLayers map
if (previousDemLayerKey) {
  managedImageryLayers.delete(previousDemLayerKey);
}

// CRITICAL FIX: Remove DEM hillshade layer from managedImageryLayers map
if (previousDemLayerKey) {
  managedImageryLayers.delete(previousDemLayerKey + ":hillshade");
}
```

### 4. Cleanup in applyDemLayer() drape removal (around line 3155)
```javascript
// CRITICAL FIX: Remove old DEM drape layer from managedImageryLayers map
if (activeDemContext && activeDemContext.layerKey) {
  managedImageryLayers.delete(activeDemContext.layerKey);
}
```

### 5. Cleanup in applyDemLayer() hillshade removal (multiple locations)
```javascript
// CRITICAL FIX: Remove old DEM hillshade layer from managedImageryLayers map
if (activeDemContext && activeDemContext.layerKey) {
  managedImageryLayers.delete(activeDemContext.layerKey + ":hillshade");
}
```

## Expected Result
After this fix:
- ✅ **Table reordering**: Still works (already fixed)
- ✅ **Text visibility**: Still works (already fixed)  
- ✅ **Map reordering**: Now works for both DEM and imagery layers

DEM layers will now be found by the `reorderLayersEventDriven()` function and can be reordered on the map in real-time along with imagery layers.

## Testing
To test the fix:
1. Load both DEM and imagery layers in the search results
2. Drag to reorder layers in the table
3. Verify that both DEM and imagery layers reorder correctly on the 3D globe
4. Check JavaScript console - should see no "Layer not found for reordering" errors

## Backward Compatibility
This fix maintains full backward compatibility:
- All existing functionality preserved
- No breaking changes to public APIs
- DEM layers continue to work exactly as before, just with added reordering capability