
    
    

with dbt_test__target as (

  select transaction_id as unique_field
  from `gen-lang-client-0635762262`.`analytics`.`stg_transactions`
  where transaction_id is not null

)

select
    unique_field,
    count(*) as n_records

from dbt_test__target
group by unique_field
having count(*) > 1


