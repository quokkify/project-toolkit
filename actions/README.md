# Composite actions

The MVP intentionally contains no composite `action.yml`. Reusable workflows own job-level CI, while Copier generates caller files. A composite action will be introduced only when repeated **step-level** logic cannot be represented clearly with established third-party Actions or ordinary workflow steps.
