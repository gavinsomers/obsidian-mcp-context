{% macro reset_warehouse_schemas() -%}
  {% set schemas = ["staging", "intermediate", "dim", "fact", "mart", "marts"] %}
  {% for schema in schemas %}
    {% do run_query("drop schema if exists " ~ schema ~ " cascade") %}
  {% endfor %}
{%- endmacro %}
