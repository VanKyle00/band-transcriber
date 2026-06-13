import SubmitForm from "@/components/SubmitForm";

export default function Home() {
  return (
    <>
      <h1>Turn a song into stems + sheet music</h1>
      <p className="lede">
        Upload an audio file or paste a YouTube link. We separate drums, bass, and vocals
        (plus best-effort guitar &amp; piano), then transcribe each stem into sheet music,
        tablature, MIDI/MusicXML, and an interactive piano roll.
      </p>
      <SubmitForm />
    </>
  );
}
