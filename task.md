# Task List: Insight Layer & Deep Linking

- [x] **Backend Implementation**
    - [x] Update `schema.sql` with new columns (`is_insight`, `article_url`)
    - [x] Update `app.py`: `migrate_d1_schema` function
    - [x] Update `app.py`: `insert_layer` and `update_layer` functions
    - [x] Update `app.py`: `/admin/upload` (POST) and `/admin/update/<id>` (PUT) routes

- [x] **Admin UI Implementation**
    - [x] Update `templates/admin.html`: Add fields to Upload Form
    - [x] Update `templates/admin.html`: Add fields to Edit Modal
    - [x] Update `templates/admin.html`: Update JS for form submission and modal data population

- [ ] **Frontend Implementation**
    - [x] Create `templates/popup.html` (Glassmorphism Modal)
    - [ ] Update `templates/index.html`: Add "View Insight" button to layer details
    - [x] Update `static/js/app.js`: Implement Deep Linking (`updateUrlParams`, `loadFromUrlParams`)
    - [ ] Update `static/js/app.js`: Revert Layer Card Click Handler & Implement Button Handler
    - [x] Update `static/js/app.js`: Implement Modal Logic (`openInsightModal`, `closeInsightModal`)

- [ ] **Verification**
    - [ ] Verify Database Migration
    - [ ] Verify Admin Upload & Edit flows
    - [ ] Verify Frontend Insight Modal interaction
    - [ ] Verify Deep Linking functionality
