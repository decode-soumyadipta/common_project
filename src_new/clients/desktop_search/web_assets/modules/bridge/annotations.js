  window.offlineGIS = window.offlineGIS || {};
  Object.assign(window.offlineGIS, {
      clearAnnotations: function () {
        if (typeof clearAnnotationEntities === "function") {
          clearAnnotationEntities();
        }
      },
      setAnnotationVisibility: function (visible) {
        setAnnotationVisibility(Boolean(visible));
      },
      addIconAnnotation: function (lon, lat, iconName, text) {
        if (!viewer) return;
        annotationCounter += 1;
        const annotationId = "icon-annotation-" + String(annotationCounter);
        const displayText = String(text || "").trim() || "Label";
        
        // Map icon names to QGIS-style SVG data URIs
        const iconMap = {
          "marker": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23e74c3c' d='M12 2C8.13 2 5 5.13 5 9c0 5.25 7 13 7 13s7-7.75 7-13c0-3.87-3.13-7-7-7zm0 9.5c-1.38 0-2.5-1.12-2.5-2.5s1.12-2.5 2.5-2.5 2.5 1.12 2.5 2.5-1.12 2.5-2.5 2.5z'/%3E%3C/svg%3E",
          "flag": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23f39c12' d='M14.4 6L14 4H5v17h2v-7h5.6l.4 2h7V6z'/%3E%3C/svg%3E",
          "star": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23f1c40f' d='M12 17.27L18.18 21l-1.64-7.03L22 9.24l-7.19-.61L12 2 9.19 8.63 2 9.24l5.46 4.73L5.82 21z'/%3E%3C/svg%3E",
          "home": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%233498db' d='M10 20v-6h4v6h5v-8h3L12 3 2 12h3v8z'/%3E%3C/svg%3E",
          "info": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%2327ae60' d='M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-6h2v6zm0-8h-2V7h2v2z'/%3E%3C/svg%3E",
          "warning": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%23e67e22' d='M1 21h22L12 2 1 21zm12-3h-2v-2h2v2zm0-4h-2v-4h2v4z'/%3E%3C/svg%3E",
          "camera": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%239b59b6' d='M9 2L7.17 4H4c-1.1 0-2 .9-2 2v12c0 1.1.9 2 2 2h16c1.1 0 2-.9 2-2V6c0-1.1-.9-2-2-2h-3.17L15 2H9zm3 15c-2.76 0-5-2.24-5-5s2.24-5 5-5 5 2.24 5 5-2.24 5-5 5z'/%3E%3C/svg%3E",
          "tree": "data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='24' height='24' viewBox='0 0 24 24'%3E%3Cpath fill='%2327ae60' d='M16.5 12c.83 0 1.5-.67 1.5-1.5 0-.83-.67-1.5-1.5-1.5-.83 0-1.5.67-1.5 1.5 0 .83.67 1.5 1.5 1.5zM9 11c.55 0 1-.45 1-1s-.45-1-1-1-1 .45-1 1 .45 1 1 1zm0 3c-.55 0-1 .45-1 1s.45 1 1 1 1-.45 1-1-.45-1-1-1zm6.5 2c-.83 0-1.5.67-1.5 1.5s.67 1.5 1.5 1.5 1.5-.67 1.5-1.5-.67-1.5-1.5-1.5zM11 19h2v3h-2z'/%3E%3C/svg%3E",
        };
        
        const iconImage = iconMap[iconName] || iconMap["marker"];
        
        let anchorPosition = null;
        if (lastMapClickCartesian) {
          const lastLonLat = cartesianToLonLat(lastMapClickCartesian);
          if (lastLonLat) {
            const lonDiff = Math.abs(Number(lastLonLat.lon) - Number(lon));
            const latDiff = Math.abs(Number(lastLonLat.lat) - Number(lat));
            if (lonDiff <= 0.00002 && latDiff <= 0.00002) {
              anchorPosition = Cesium.Cartesian3.clone(lastMapClickCartesian);
            }
          }
        }
        if (!anchorPosition) {
          const cartographic = Cesium.Cartographic.fromDegrees(Number(lon), Number(lat));
          const sampledHeight = viewer.scene && viewer.scene.globe ? viewer.scene.globe.getHeight(cartographic) : null;
          const height = Number.isFinite(sampledHeight) ? Number(sampledHeight) : 0.0;
          anchorPosition = Cesium.Cartesian3.fromDegrees(Number(lon), Number(lat), height);
        }
        lastMapClickCartesian = null;
        
        // Icon billboard
        const iconEntity = viewer.entities.add({
          position: anchorPosition,
          billboard: {
            image: iconImage,
            width: 32,
            height: 32,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.5),
          },
        });
        iconEntity.show = annotationVisibilityEnabled;
        iconEntity._annotationId = annotationId;
        iconEntity._annotationRole = "icon";
        
        // Text label
        const labelEntity = viewer.entities.add({
          position: anchorPosition,
          label: {
            text: displayText,
            fillColor: Cesium.Color.WHITE,
            showBackground: true,
            backgroundColor: Cesium.Color.BLACK.withAlpha(0.7),
            outlineColor: Cesium.Color.BLACK.withAlpha(0.9),
            outlineWidth: 2,
            style: Cesium.LabelStyle.FILL_AND_OUTLINE,
            font: "600 13px 'Segoe UI', 'Helvetica Neue', sans-serif",
            pixelOffset: new Cesium.Cartesian2(0, -40),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1800000.0, 0.45),
            translucencyByDistance: new Cesium.NearFarScalar(3000.0, 1.0, 2400000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        labelEntity.show = annotationVisibilityEnabled;
        labelEntity._annotationId = annotationId;
        labelEntity._annotationRole = "label";
        
        // Edit button
        const editEntity = viewer.entities.add({
          position: anchorPosition,
          billboard: {
            image: ANNOTATION_EDIT_ICON_IMAGE,
            width: 17,
            height: 17,
            color: Cesium.Color.WHITE.withAlpha(0.42),
            pixelOffset: new Cesium.Cartesian2(-20, -58),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        editEntity.show = annotationVisibilityEnabled;
        editEntity._annotationId = annotationId;
        editEntity._annotationRole = "edit";
        editEntity._annotationIconEntity = iconEntity;
        editEntity._annotationLabelEntity = labelEntity;
        
        // Delete button
        const deleteEntity = viewer.entities.add({
          position: anchorPosition,
          billboard: {
            image: ANNOTATION_DELETE_ICON_IMAGE,
            width: 17,
            height: 17,
            color: Cesium.Color.WHITE.withAlpha(0.62),
            pixelOffset: new Cesium.Cartesian2(20, -58),
            horizontalOrigin: Cesium.HorizontalOrigin.CENTER,
            verticalOrigin: Cesium.VerticalOrigin.BOTTOM,
            scaleByDistance: new Cesium.NearFarScalar(2500.0, 1.0, 1700000.0, 0.62),
            disableDepthTestDistance: Number.POSITIVE_INFINITY,
          },
        });
        deleteEntity.show = annotationVisibilityEnabled;
        deleteEntity._annotationId = annotationId;
        deleteEntity._annotationRole = "delete";
        deleteEntity._annotationIconEntity = iconEntity;
        deleteEntity._annotationLabelEntity = labelEntity;
        deleteEntity._annotationEditEntity = editEntity;
        
        annotationEntities.push(iconEntity);
        annotationEntities.push(labelEntity);
        annotationEntities.push(editEntity);
        annotationEntities.push(deleteEntity);
        requestSceneRender();
        log("info", "Icon annotation added: " + iconName + " at lon=" + lon + " lat=" + lat);
      },
  });

  function setAnnotationEditIconHoverState(editEntity, hovered) {
    if (!editEntity || !editEntity.billboard) {
      return;
    }
    editEntity.billboard.color = hovered ? Cesium.Color.WHITE.withAlpha(0.96) : Cesium.Color.WHITE.withAlpha(0.42);
  }

  function setAnnotationDeleteIconHoverState(deleteEntity, hovered) {
    if (!deleteEntity || !deleteEntity.billboard) return;
    deleteEntity.billboard.color = hovered ? Cesium.Color.WHITE.withAlpha(0.96) : Cesium.Color.WHITE.withAlpha(0.62);
  }

  function renameAnnotationFromEditIcon(editEntity) {
    if (!editEntity || editEntity._annotationRole !== "edit") {
      return false;
    }
    const labelEntity = editEntity._annotationLabelEntity || null;
    if (!labelEntity || !labelEntity.label) {
      return false;
    }
    const currentText = readLabelText(labelEntity) || "Point";
    const nextText = window.prompt("Rename annotation", currentText);
    if (nextText === null) {
      return true;
    }
    const cleaned = String(nextText).trim();
    if (!cleaned) {
      return true;
    }
    labelEntity.label.text = cleaned;
    setStatus("Point renamed: " + cleaned);
    requestSceneRender();
    return true;
  }

  function updateAnnotationHover(screenPosition) {
    if (!viewer || !screenPosition) {
      return;
    }
    const picked = viewer.scene.pick(screenPosition);
    const nextHover = picked && picked.id && picked.id._annotationRole === "edit" ? picked.id : null;
    if (hoveredAnnotationEditEntity !== nextHover) {
      if (hoveredAnnotationEditEntity) setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, false);
      hoveredAnnotationEditEntity = nextHover;
      if (hoveredAnnotationEditEntity) setAnnotationEditIconHoverState(hoveredAnnotationEditEntity, true);
    }
    const nextDelHover = picked && picked.id && picked.id._annotationRole === "delete" ? picked.id : null;
    if (hoveredAnnotationDeleteEntity !== nextDelHover) {
      if (hoveredAnnotationDeleteEntity) setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, false);
      hoveredAnnotationDeleteEntity = nextDelHover;
      if (hoveredAnnotationDeleteEntity) setAnnotationDeleteIconHoverState(hoveredAnnotationDeleteEntity, true);
    }
    requestSceneRender();
  }

