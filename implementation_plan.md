# Implementation Plan - Insight Layer & Deep Linking

## Goal Description
Add an "Insight" feature to map layers. insightful layers (`is_insight=True`) will have a special behavior: clicking their **Layer Card in the sidebar** will trigger a "Beautiful Popup" (Modal) displaying a "View Article" button linking to `article_url`, instead of just expanding the details.
The "Toggle Switch" will still function normally to show/hide the layer on the map.
Additionally, implement deep linking so the active layer (and potentially the open insight modal) state is reflected in the URL for easy sharing.

## User Review Required
> [!IMPORTANT]
> - "Insight" popup is a **Sidebar Interaction**. It overrides the default "Expand Details" behavior for insight layers.
> - URL structure will use `?layers=layer_id1,layer_id2`.
> - **Design**: The popup will be a glassmorphism modal, centered, with Title, Description, and a prominent "Read Article on MahaInsight" CTA button.

## Proposed Changes

### Database & Backend
#### [MODIFY] `schema.sql`
- Add `is_insight` (BOOLEAN) and `article_url` (TEXT) columns to `map_layers` table.

#### [MODIFY] `app.py`
- Update `migrate_d1_schema` to add new columns if missing.
- Update `insert_layer` and `update_layer` to handle `is_insight` and `article_url`.
- Update `/admin/upload` (POST) and `/admin/update/<id>` (PUT) routes to accept these fields.

### Admin UI
#### [MODIFY] `templates/admin.html`
- **Upload Form**: Add "Insight Layer" checkbox and "Article URL" input.
- **Edit Modal**: Add corresponding fields.
- **JS**: Handle these new fields in form submissions and modal population.

### Frontend (Map & Logic)
#### [NEW] `templates/popup.html`
- Create a new template file for the Insight Modal structure.
- Design: Glassmorphism backdrop, centered card, animated entry.
- Content: Dynamic Title, Description, "View on MahaInsight" Button.

#### [MODIFY] `templates/index.html`
- **Layer Loop**: In the sidebar list, add `data-is-insight="{{ layer.is_insight }}"` and `data-article-url="{{ layer.article_url }}"` to the `.layer-card` or its click target.
- **Include Popup**: Use `{% include 'popup.html' %}` to inject the modal structure.

#### [MODIFY] `static/js/app.js`
- **Deep Linking**:
    - Implement `updateUrlParams()`: Update URL when layers are toggled.
    - Implement `loadFromUrlParams()`: Parse URL on load and activate layers.
- **Layer Card Interaction**:
    - Modify `toggleLayerDetail(element, event)`:
    - Check if the layer has `isInsight`.
    - If YES: Prevent default expansion (optional) and **Open Insight Modal**.
    - If NO: Continue with default expansion.
- **Modal Logic**:
    - Functions to `openInsightModal(title, desc, url)` and `closeInsightModal()`.


## Verification Plan

### Manual Verification
1.  **Database Migration**: Run app, check logs for "Migrating: Adding is_insight...".
2.  **Admin Upload**:
    - Upload a CSV (as GeoJSON).
    - Check "Insight Layer" and enter a dummy URL (e.g., `https://google.com`).
    - Verify layer appears in Admin list.
3.  **Admin Edit**:
    - Edit an existing layer, toggle "Insight", add URL. Save. Refesh to verify persistence.
4.  **Insight Interaction**:
    - Go to map. Click the **Layer Card** (not the toggle) of the Insight layer.
    - Verify the **Insight Modal** appears (Beautiful, Glassmorphism).
    - Verify "View Article" button links correctly.
    - Verify clicking non-insight layer card (box) still expands details normally.
5.  **Deep Linking**:
    - Activate layers, check URL `?layers=slug-1,slug-2`.
    - Reload page with params -> Layers should auto-activate.
