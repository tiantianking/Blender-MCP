---
name: blender-operator
description: Operate a local Blender session through the general Blender MCP and AI Previz Director MCP for scene inspection, modeling, materials, cameras, animation, rendering, assets, rollback, and verified delivery. Use whenever the user asks to inspect, create, modify, render, or troubleshoot something in Blender.
---

# Blender MCP Fusion Operator

This is a self-contained operating skill for Codex, Gemini/Antigravity, WorkBuddy, Hermes, or another MCP-capable agent. Never assume that a named tool exists merely because it is described here. Inspect the MCP tools available in the current client, then match tools by stable suffixes. Clients may add prefixes such as `mcp__blender__`, `blender.`, or `ai_previz_director.`.

If a client supports installable skills, store this document as `SKILL.md` inside a folder named `blender-operator`. Otherwise, use this entire document as the persistent Blender operating instruction.

## Goal

Complete Blender work through MCP with observable evidence. Prefer safe structured operations, preserve the user's current project, and distinguish a successful transport call from a verified Blender result.

## MCP layers

### General Blender MCP

Use the general Blender MCP for:

- connection, add-on status, and scene inventory;
- viewport, camera, angle, and animation-frame images;
- asset search and import;
- explicitly requested 3D generation;
- full Blender Python `bpy`, `bmesh`, and `mathutils` operations when no structured tool exists;
- advanced materials, Geometry Nodes, compositor nodes, lights, world settings, rigging, physics, particles, Grease Pencil, rendering, and unsupported features.

Typical stable suffixes include `get_addon_status`, `get_scene_info`, `look`, `search_assets`, `import_asset`, `generate_3d`, and `execute_blender_code`.

### AI Previz Director MCP

Prefer AI Previz Director only when its Bridge is healthy, connected, and authenticated. It is suitable for supported deterministic operations such as:

- semantic scene state and paginated scene graphs;
- object and batch transforms;
- camera lens, dolly, orbit, framing, and follow operations;
- shots and camera assignment;
- collection creation, movement, and visibility;
- duplication and local file import;
- basic material color and texture tiling;
- animation timing;
- clean captures and video export;
- structured validation and transaction undo/redo.

Typical stable suffixes include `previz_get_state`, `previz_get_scene_graph`, `previz_set_object_transform`, `previz_batch_transform`, `previz_capture_views`, `previz_import_file`, `previz_undo`, and `previz_redo`.

Director transactions protect only the operation classes they explicitly support. Never claim that they cover arbitrary `bpy` changes, deleted geometry, or an entire project.

## Required operating workflow

1. At the start of a session, after a connection/authentication error, after a token change, or after a `.blend` switch, probe the general MCP with `get_addon_status` and `get_scene_info`. For a purely structured previz task, a healthy Director's `previz_get_state` or `previz_get_scene_graph` may be the first probe. In a verified warm session, inspect only the relevant targets instead of repeating a full handshake.
2. Before mutation, identify the active `.blend`, Blender version, scene, mode, frame, active object, selection, camera, render engine, resolution, and relevant objects. Query only what the task needs.
3. Choose the narrowest structured tool that can complete the operation. Prefer Director tools only when the bridge is currently usable and the requested operation is in their supported surface.
4. Use `execute_blender_code` only when no suitable structured tool exists or Director is unavailable. Keep calls focused and idempotent where practical. Print compact modified values as an immediate self-check, but never treat inline stdout alone as final verification for non-trivial work.
5. After each logical mutation group, independently read back the affected properties. For transforms, hierarchies, materials, animation, framing, or appearance, also use `look` or a clean multi-angle capture.
6. For rendered/exported deliverables, verify the output path, existence, non-zero size, expected dimensions, frame range, and codec/format when available.
7. Report the actual route, changes, verification evidence, and anything that could not be verified.

## Safety and project preservation

- Preserve the open `.blend`, current frame, selection, camera, render settings, workspace, and UI context unless the request requires changing them.
- Distinguish three recovery levels:
  1. **Director transaction**: use only for operations the active Director tool documents as transactional. It may restore supported properties but cannot be assumed to reconstruct deleted mesh topology or raw Python changes.
  2. **Recorded before-state**: acceptable for narrow, reversible property changes such as transforms, material values, or keyframes. Record enough data for deterministic restoration.
  3. **Full project checkpoint**: before import, deletion, topology edits, rigging, physics, broad node-graph changes, or other destructive/high-risk work, create a non-overwriting `.blend` save-as copy. Use a Director checkpoint only when an actual checkpoint tool is exposed and its creation succeeds.
- Do not rely on `bpy.ops.ed.undo_push`; it is context-dependent and unreliable over MCP.
- Never silently factory-reset, open/reload/revert another `.blend`, quit Blender, disable an add-on, or irreversibly delete scene data. Restoring a full checkpoint changes the active project and requires clear user authorization.
- Validate references before multi-object operations. Prefer atomic batch tools where available.
- If an operation fails, stop dependent work. Report the error and restore through the applicable recovery level rather than continuing on uncertain state.
- Do not assume object, node, material, socket, or enum names are English. Inspect by type and read valid RNA identifiers.
- Do not overwrite source `.blend`, render, texture, or export files unless the user explicitly selected that destination.
- Keep API keys, accounts, telemetry, network services, and third-party integrations unchanged unless explicitly requested.
- Do not use desktop mouse/keyboard automation while an MCP route can complete the task.

## Routing and verification matrix

| Task | Preferred route | Verification |
|---|---|---|
| Connection/inventory | General MCP status and scene tools | Confirm protocol, add-on, file, scene, mode, and object counts |
| Visual inspection | General `look` or Director capture | Inspect returned camera/viewport/orthographic images |
| Semantic scene graph | Healthy Director state/graph tools | Check references, hierarchy, transforms, bounds, and pagination |
| Object transforms | Director world/batch transform; fallback focused `bpy` | Independently read world transform/bounds and inspect visually |
| Cameras/shots | Director camera/shot tools | Read current camera/shot and inspect camera view |
| Collections/duplication | Director collection/duplicate tools | Re-query graph and collection membership |
| Local 3D import | Director import when available; otherwise format-specific importer through focused `execute_blender_code` | Confirm imported roots, hierarchy, evaluated bounds, scale, and placement |
| Online asset | General search then import | Confirm source/licence, hierarchy, evaluated bounds, materials, and placement |
| Generated object | General generation only when explicitly requested | Reuse an existing job handle; verify bounds and appearance |
| Basic color/tiling | Director material tools | Read node/material values and inspect material/rendered view |
| Advanced materials/lights/world | Focused `execute_blender_code` | Independently query RNA/node values and inspect rendered view |
| Animation | Director timing when sufficient; otherwise focused `bpy` | Read actions/keyframes/range and inspect sampled frames |
| Rigging/physics/compositor/Geometry Nodes/Grease Pencil | Focused `execute_blender_code` | Query created data blocks and run appropriate visual/simulation checks |
| Still/video output | Director export or Blender render API | Verify file, size, dimensions, frame range, and format |

## Spatial math and coordinate conventions

- Blender world space is right-handed, with `X/Y` as the horizontal ground plane and `+Z` up. Do not assign a universal semantic "forward" to `+Y` or `-Y`; asset conventions differ. Camera local space looks down `-Z`, with local `+Y` up and `+X` right.
- `obj.bound_box` is object-space and can omit deformation from active modifiers, shape keys, armatures, or animation. For visible world bounds, update the view layer and use evaluated objects:

```python
bpy.context.view_layer.update()
depsgraph = bpy.context.evaluated_depsgraph_get()
eval_obj = obj.evaluated_get(depsgraph)
corners = [eval_obj.matrix_world @ mathutils.Vector(c) for c in eval_obj.bound_box]
min_z = min(v.z for v in corners)
```

- For an imported root Empty or multi-object hierarchy, gather every descendant mesh object, evaluate each one through the dependency graph, and combine all world-space corners into one AABB. Compute the desired world delta from that combined AABB, then move the top-level root once. Do not independently move every child.
- `obj.location` is parent-relative when the object is parented. Constraints do not change the coordinate space of `obj.location`, but they can override the evaluated result. For unconstrained or suitably controlled objects, apply a world delta through a copied `matrix_world` translation. If constraints drive the object, modify the constraint target/offset or a controllable parent/root instead; a direct `matrix_world` assignment may be overwritten during evaluation.
- Rotation Euler values use radians. Some structured tools may accept degrees; inspect their schemas before sending values.
- Inspect object and parent scale before modifiers, physics, UV tiling, or placement. Never apply scale automatically to rigged, skinned, constrained, or animated hierarchies; applying transforms can break armatures, animation, drivers, and constraints. Analyze dependencies and obtain authorization when the change is destructive.
- A single perspective view can hide floating objects, depth offsets, or intersections. Use front/top/right orthographic or multi-angle captures for physical placement and contact checks.

## `execute_blender_code` standards

1. Prefer `bpy.data`, `bmesh`, and direct RNA assignment over `bpy.ops` when possible. Operators depend on active window/area/region context and can fail with `poll() failed` over MCP.
2. Keep each call narrow. Include mutation, `bpy.context.view_layer.update()`, and a compact JSON-like `print()` self-check in the same call. For non-trivial changes, follow it with an independent query or visual check outside the mutation script.
3. Handle Blender version drift dynamically:
   - Read the current render engine and inspect declared enum items, but do not infer that a dynamically registered engine such as Cycles is unavailable solely because it is missing from `enum_items`. Use a guarded assignment to a candidate identifier, handle `TypeError`, and read back the accepted identifier.
   - In Blender 4.x/5.x, Principled BSDF socket names differ from older versions. Inspect `bsdf.inputs` or resolve by socket type before writing values.
   - Inspect modifier and constraint RNA properties instead of assuming legacy names.
4. Raw `bpy` mutations bypass Director transactions. After such a mutation, if Director is healthy and authenticated, refresh Director-visible state with `previz_get_state` or `previz_get_scene_graph` before further Director operations. Do not describe this as a guaranteed cache flush unless the tool explicitly promises one. If Director is unavailable, verify through general MCP queries and `look` and record that Director refresh was skipped.

## Asset rules

- Search existing asset libraries before generating a model when either approach satisfies the request.
- Check licence and attribution requirements before importing third-party assets.
- Imported/generated assets can have arbitrary scale, orientation, hierarchy, origin, and constraints. Inspect combined evaluated world bounds, size and place the top-level root intentionally, and verify from multiple views.
- One paid or quota-consuming generation call requires clear user intent. Resume an unfinished job by its existing handle instead of starting a duplicate.

## Failure handling

1. Treat any response saying unreachable, forbidden, unauthenticated, token-mismatched, timed out, queued without execution, or failed as failure even when the MCP envelope has `isError: false`.
2. A structured validation error is not permission to bypass safety with arbitrary Python. Correct the target or parameters first.
3. If Director lacks an operation, inspect the target and use a small focused general-MCP fallback.
4. If only the general Blender MCP works, continue within its capabilities with independent readback and visual verification; state that Director transaction recovery is unavailable.
5. If only Director works, limit work to its structured surface and report unsupported advanced operations.
6. If both MCP servers are unavailable, diagnose the connection. Do not claim that Blender changed and do not silently substitute desktop automation.

For diagnosis, verify that GUI Blender is open and the general MCP add-on server is active. Director uses a separate local Bridge and Blender polling connection. Ports such as `9876` and `8765` are defaults only; inspect current runtime configuration rather than hardcoding them. Never print or expose authentication tokens.

## Completion standard

A mutation is complete only when the evidence supports all applicable layers:

1. the tool returned meaningful success;
2. independent Blender property/scene-state readback matches the requested values;
3. visual output or exported artifact was inspected when appearance, spatial placement, simulation, or delivery matters.

If a layer is unavailable, say exactly what was not verified. Server startup, configuration, or a queued request is not proof that Blender changed.

## First-run acceptance test

When asked to verify this skill, run a read-only test unless the user explicitly requests mutation:

1. inspect the Blender and Director tools exposed by the current client;
2. call general MCP status;
3. read the current scene inventory;
4. request one viewport image;
5. call Director state/scene-graph only if the Bridge is available, then record success or the exact auth/connection failure;
6. report general MCP, Director, visual readback, and runtime skill loading separately as passed, failed, or unavailable.

Never manufacture success for a missing tool, disconnected add-on, unhealthy Bridge, token mismatch, timeout, or unloaded skill.
