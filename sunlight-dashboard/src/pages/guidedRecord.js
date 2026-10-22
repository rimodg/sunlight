export function guidedBatch(form,publicationTime=new Date()){
 const money=form.metric==='payment';
 if(!form.source_id)throw new Error('Register and select a source first.');
 if(!form.expected_value)throw new Error('An expected measurement is required.');
 if(!money&&!form.unit.trim())throw new Error('Specify the physical unit.');
 const timestamp=value=>{const date=new Date(value);if(!value||!Number.isFinite(date.getTime()))throw new Error('Provide valid due and observation dates.');return date.toISOString()};
 const measure={metric:form.metric,unit:money?'currency':form.unit.trim(),currency:money?form.currency.trim().toUpperCase():null,period_start:form.period_start,period_end:form.period_end};
 const revision=Number(form.revision);
 if(!Number.isInteger(revision)||revision<1)throw new Error('Revision must be a positive whole number.');
 const event={event_id:`${form.contract_id}/${form.item_id}/v${revision}`,contract_id:form.contract_id,item_id:form.item_id,revision,title:form.title,category:form.category,origin_country:form.origin_country,destination_country:form.destination_country,published_at:publicationTime.toISOString(),expected:{...measure,value:form.expected_value,due_at:timestamp(form.due_at),document_url:form.expected_document},observed:form.observed_value.trim()===''?null:{...measure,value:form.observed_value,observed_at:timestamp(form.observed_at),document_url:form.observed_document}};
 return {source_id:form.source_id,events:[event]};
}
