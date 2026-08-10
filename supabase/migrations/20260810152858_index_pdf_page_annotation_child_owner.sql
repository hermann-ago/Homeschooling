create index ix_pdf_page_annotations_child_owner
  on app.pdf_page_annotations(child_id, owner_id);
