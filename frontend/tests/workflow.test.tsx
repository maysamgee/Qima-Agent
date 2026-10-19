import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import { MemoryRouter } from 'react-router-dom';
import { describe, expect, it, vi } from 'vitest';
import { AgentCards } from '../src/components';
import { DraftEditor } from '../src/CandidateDetail';
import type { Draft } from '../src/types';
const draft: Draft = {id:'draft-1',subject:'Coffee relationship',body:'Hello producer team',version:1,approval_status:'APPROVED',channel:'EMAIL',model_id:'mock',prompt_version:'sourcing-v1',evidence_ids:[]};
describe('Human controlled outreach', () => {
  it('makes the selected business objective explicit in navigation', () => {
    render(<MemoryRouter><AgentCards/></MemoryRouter>);
    expect(screen.getByRole('link',{name:/Find Buyers/})).toHaveAttribute('href','/discover?mode=LEAD');
    expect(screen.getByRole('link',{name:/Find Suppliers/})).toHaveAttribute('href','/discover?mode=SOURCING');
  });
  it('blocks sending after edits until the revision is saved and approved', async () => {
    const run = vi.fn();render(<DraftEditor draft={draft} run={run} pending={false}/>);
    const send = screen.getByRole('button',{name:'Send simulated email'});
    expect(send).toBeEnabled();
    await userEvent.type(screen.getByLabelText('Message'), ' Additional question.');
    expect(send).toBeDisabled();
    await userEvent.click(screen.getByRole('button',{name:'Save draft changes'}));
    expect(run).toHaveBeenCalledWith(expect.objectContaining({method:'PATCH',body:expect.objectContaining({expected_version:1})}));
  });
  it('requires approval for a newly generated draft', () => {
    render(<DraftEditor draft={{...draft,approval_status:'PENDING'}} run={vi.fn()} pending={false}/>);
    expect(screen.getByRole('button',{name:'Send simulated email'})).toBeDisabled();
    expect(screen.getByRole('button',{name:'Approve this version'})).toBeEnabled();
  });
  it('offers only manual record controls for Instagram', () => {
    render(<DraftEditor draft={{...draft,channel:'INSTAGRAM'}} run={vi.fn()} pending={false}/>);
    expect(screen.queryByRole('button',{name:'Send simulated email'})).not.toBeInTheDocument();
    expect(screen.getByRole('button',{name:'Record manually sent'})).toBeEnabled();
  });
});
