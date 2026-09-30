import assert from 'node:assert/strict';
import { test } from 'node:test';
import { bookingActions, createSocialApi, harvestWindow, hasFeature, instant, mergeMessages } from '../src/services/social-contracts.ts';
const id = '11111111-1111-4111-8111-111111111111';
const other = '22222222-2222-4222-8222-222222222222';
test('harvest windows are Kenya dates, reject invalid calendar dates and past requests', () => {
  assert.deepEqual(harvestWindow('2027-01-02', '2027-01-02', 0), {window_start:'2027-01-02T05:00:00.000Z',window_end:'2027-01-02T15:00:00.000Z'});
  assert.throws(() => harvestWindow('2027-02-29','2027-03-01',0));
  assert.throws(() => harvestWindow('2027-03-01','2027-02-28',0));
  assert.throws(() => harvestWindow('2027-01-02','2027-01-02',Date.parse('2027-01-03')));
});
test('pending, unverified, expired and inactive-plan subscriptions never unlock features', () => {
  const plan={id,active:true,features:['prebooking']};
  const sub={plan_id:id,status:'active',verified_at:'2027-01-01T00:00:00',current_period_end:'2027-02-01T00:00:00'};
  const now=Date.parse('2027-01-15');
  assert.equal(hasFeature([sub],[plan],'prebooking',now),true);
  for(const patch of [{status:'pending'},{verified_at:null},{current_period_end:'2027-01-01'}]) assert.equal(hasFeature([{...sub,...patch}],[plan],'prebooking',now),false);
  assert.equal(hasFeature([sub],[{...plan,active:false}],'prebooking',now),false);
  assert.equal(hasFeature([sub],[plan],'insights',now),false);
});
test('message history merges overlapping pages without duplicates and respects UTC timestamps',()=>{
  const a={id,created_at:'2027-01-01T12:00:00'};
  const b={id:other,created_at:'2027-01-01T14:00:00+03:00'};
  assert.deepEqual(mergeMessages([a],[b,a]).map(x=>x.id),[other,id]);
  assert.equal(instant(a.created_at),Date.parse(a.created_at+'Z'));
});
test('harvest actions are restricted to the participant and current state',()=>{
 const booking={buyer_id:id,farmer_id:other,status:'requested'};
 assert.deepEqual(bookingActions(booking,id),['cancelled']);
 assert.deepEqual(bookingActions(booking,other),['accepted','rejected']);
 assert.deepEqual(bookingActions(booking,'stranger'),[]);
 assert.deepEqual(bookingActions({...booking,status:'accepted'},other),['fulfilled']);
 assert.deepEqual(bookingActions({...booking,status:'fulfilled'},id),[]);
});
test('message retries retain their client identity and invalid messages never reach the server',async()=>{
 const calls=[]; const api=createSocialApi(async(path,options)=>{calls.push({path,options});return {};});
 await api.send(id,other,' Hello '); await api.send(id,other,'Hello');
 assert.deepEqual(calls[0],calls[1]); assert.equal(calls[0].options.body.client_message_id,other);
 assert.throws(()=>api.send(id,other,' ')); assert.throws(()=>api.send(id,other,'x'.repeat(4001)));
 assert.equal(calls.length,2);
});
test('history paging is newest first and transitions carry the server version',async()=>{
 const calls=[]; const api=createSocialApi(async(path,options)=>{calls.push({path,options});return {};});
 await api.messages(id,other); assert.match(calls[0].path,/latest_first=true.*cursor=/);
 await api.transitionBooking({id,version:7},'accepted'); assert.equal(calls[1].options.body.expected_version,7);
 await api.subscribe(id,'persistent-attempt'); assert.equal(calls[2].options.idempotencyKey,'persistent-attempt');
});
