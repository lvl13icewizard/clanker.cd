import { useEffect, useRef, useState } from 'react';
import './listening-room.css';

const RECORDS = [
  { name: 'Andrew', slug: 'andrew', issue: '018', title: 'Glass Field', light: '#c08a66', glow: '#e3b99a' },
  { name: 'Mara', slug: 'electronic', issue: '013', title: 'Night Ferry', light: '#77989e', glow: '#b4d7d2' },
  { name: 'June', slug: 'altindie', issue: '011', title: 'Late Summer', light: '#a0a78b', glow: '#d5dfb6' },
  { name: 'Tasha', slug: 'pop', issue: '009', title: 'Curtain Call', light: '#b27bb4', glow: '#efb4d9' },
];
const cover = record => `/demo/${record.slug}/cover-${record.issue}.jpg`;

export default function ListeningRoom() {
  const [selected, setSelected] = useState(0);
  const [lit, setLit] = useState(true);
  const [moving, setMoving] = useState(null);
  const [reduced, setReduced] = useState(() => window.matchMedia('(prefers-reduced-motion: reduce)').matches);
  const buttons = useRef([]);
  const timer = useRef(null);
  const current = RECORDS[selected];

  useEffect(() => {
    const media = window.matchMedia('(prefers-reduced-motion: reduce)');
    const update = () => setReduced(media.matches);
    media.addEventListener('change', update);
    return () => { media.removeEventListener('change', update); clearTimeout(timer.current); };
  }, []);

  const choose = index => {
    if (index === selected) return;
    clearTimeout(timer.current);
    setSelected(index);
    setMoving(reduced ? null : index);
    if (!reduced) timer.current = setTimeout(() => setMoving(null), 760);
  };
  const navigate = (event, index) => {
    let next;
    if (event.key === 'ArrowRight') next = (index + 1) % RECORDS.length;
    if (event.key === 'ArrowLeft') next = (index + RECORDS.length - 1) % RECORDS.length;
    if (event.key === 'Home') next = 0;
    if (event.key === 'End') next = RECORDS.length - 1;
    if (next !== undefined) { event.preventDefault(); choose(next); buttons.current[next].focus(); }
  };

  return <figure className={`lr-room${lit ? ' lr-lights-on' : ''}`} aria-label="The clanker's listening room" style={{ '--room-light': current.light, '--room-glow': current.glow }}>
    <div className="lr-scene">
      <img className="lr-room-art" src="/room/listening-room-v1.png" width="1254" height="1254" fetchpriority="high" alt="Clanker in headphones, curled up in a listening chair beside a record player and a cabinet full of records." />
      <div className="lr-wall-light" aria-hidden="true" />
      <div className="lr-lamp-light" aria-hidden="true" />
      <div className="lr-records" role="group" aria-label="Choose a record for the room">
        {RECORDS.map((record, index) => <button type="button" key={record.slug} className={`lr-wall-record${selected === index ? ' lr-selected' : ''}`} style={{ '--record-x': `${16 + index * 19}%` }} ref={element => { buttons.current[index] = element; }} onClick={() => choose(index)} onKeyDown={event => navigate(event, index)} aria-pressed={selected === index} aria-label={`Put on ${record.title}, ${record.name}'s demo issue ${record.issue}`} title={`${record.title} · ${record.name}`}>
          <img src={cover(record)} alt="" width="640" height="640" draggable="false" />
          <span className="lr-record-edge" aria-hidden="true" />
        </button>)}
      </div>
      <button className="lr-lamp-switch" type="button" aria-label={lit ? 'Turn off the room lighting' : 'Turn on the room lighting'} aria-pressed={lit} onClick={() => setLit(!lit)} title={lit ? 'Lights off' : 'Lights on'}><span className="sr-only">Room lighting</span></button>
      <a href={`?demo=${current.slug}&view=latest`} className={`lr-on-console${moving !== null ? ' lr-arriving' : ''}`} aria-label={`Read ${current.title}, ${current.name}'s demo issue ${current.issue}`}>
        <img src={cover(current)} alt="" width="640" height="640" draggable="false" />
      </a>
      {moving !== null && <div key={moving} className="lr-flying-record" style={{ '--from-x': `${16 + moving * 19}%` }} aria-hidden="true"><img src={cover(current)} alt="" width="640" height="640" /></div>}
      <span className="lr-power-light" aria-hidden="true" />
    </div>
    <figcaption className="sr-only" aria-live="polite">Selected: {current.title}, {current.name}’s demo.</figcaption>
  </figure>;
}
