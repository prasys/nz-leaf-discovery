#!/usr/bin/env python3
"""English-only request boundary, codec round trips and fitting policy checks."""
import io
import math
import json
from pathlib import Path
import struct
import sys
import unittest
from unittest.mock import patch
import urllib.error

sys.path.insert(0,str(Path(__file__).resolve().parent))
import eleven_greeting as api
from greeting import CLIPS,CLIP_SETS,ENGLISH,EV_CLIPS,locked_text,output_path
from prepare_greeting import fit,normalise,quiet_trim,read_generated,wav_bytes
from unittest.mock import Mock
from ssc_decode import Tables,decode,Bits,coefficients
from ssc_encode import Writer,block_bits,encode,snr

SPEECH = Path.home()/"nissan/work/language-speech/rom/Speech.exe"


class RequestBoundary(unittest.TestCase):
    def test_scope_and_locked_words(self):
        self.assertEqual(set(locked_text()),set(range(764,820)))
        self.assertEqual(len(ENGLISH),56)
        self.assertTrue(all(x.isascii() for x in ENGLISH.values()))
        self.assertEqual(ENGLISH[811],"Sunday.")
        self.assertEqual(ENGLISH[819],"Don't drink and drive.")

    def test_kia_ora_is_sample_only(self):
        # Owner-facing voice comparison includes a Kia ora line; the locked
        # start-up selector has no such slot, so the full render never emits it.
        self.assertIn("Kia ora.", api.SAMPLE)
        self.assertNotIn("Kia ora.", ENGLISH.values())
        self.assertNotIn("Kia ora.", locked_text().values())
        with patch.object(api,"request",return_value=b"\0\0"*100) as request:
            api.synthesize(api.SAMPLE,"A"*20)
            request.assert_called_once()
        with patch.object(api,"request") as request:
            with self.assertRaises(ValueError):
                api.synthesize("Kia ora.","A"*20)
            request.assert_not_called()

    def test_no_key_means_no_network(self):
        with patch.dict(api.os.environ,{},clear=True),patch.object(api.urllib.request,"build_opener") as opened:
            with self.assertRaisesRegex(ValueError,"absent"):
                api.request("/v1/shared-voices")
            opened.assert_not_called()

    def test_non_locked_text_never_reaches_api(self):
        with patch.object(api,"request") as request:
            with self.assertRaises(ValueError):
                api.synthesize("not a greeting from the locked table","A"*20)
            with self.assertRaises(ValueError):
                api.synthesize("おはようございます","A"*20)
            request.assert_not_called()

    def test_only_english_text_and_generation_settings_sent(self):
        with patch.object(api,"request",return_value=b"\0\0"*100) as request:
            _,meta = api.synthesize("Hello.","A"*20)
        body = request.call_args.args[1]
        self.assertEqual(set(body),{"text","model_id","seed","voice_settings"})
        self.assertEqual(body["text"],"Hello.")
        self.assertEqual(meta["frames"],100)

    def test_http_error_body_and_headers_never_leak(self):
        error = urllib.error.HTTPError("https://api.elevenlabs.io/v1/shared-voices",401,
                                      "sensitive-message",{"xi-api-key":"fake-test-secret"},io.BytesIO(b"sensitive-body"))
        with patch.dict(api.os.environ,{"ELEVENLABS_API_KEY":"fake-test-secret"}),patch.object(
                api.urllib.request,"build_opener") as opener:
            opener.return_value.open.side_effect = error
            with self.assertRaises(ValueError) as observed:
                api.request("/v1/shared-voices")
        self.assertEqual(str(observed.exception),"ElevenLabs HTTP 401; response body omitted")

    def test_output_outside_english_directory_refused(self):
        for p in (Path.home()/"nissan/sdcard/test.wav",Path("/tmp/audio.wav")):
            with self.assertRaises(ValueError):
                output_path(p)
        with self.assertRaises(ValueError):
            output_path(Path.home()/"nissan/work/language-speech/en-greeting/test.wav","ev")

    def test_ev_scope_and_locked_words(self):
        self.assertEqual(set(locked_text("ev")),set(EV_CLIPS))
        self.assertEqual(len(EV_CLIPS),41)
        self.assertNotIn(443,EV_CLIPS)
        self.assertTrue(all(x.isascii() for x in locked_text("ev").values()))
        self.assertEqual(locked_text("ev")[1297],"Battery charge is low.")
        self.assertEqual(locked_text("ev")[1745],"Displaying energy economy information.")
        self.assertEqual(locked_text("ev")[1746],"Displaying the power consumption meter.")
        self.assertEqual(locked_text("ev")[1722],"Update charging stations.")
        self.assertEqual(CLIP_SETS["greeting"],tuple(range(764,820)))

    def test_clip_set_text_boundary(self):
        with patch.object(api,"request",return_value=b"\0\0"*100) as request:
            api.synthesize("Battery charge is low.","A"*20,"ev")
            request.assert_called_once()
        with patch.object(api,"request") as request:
            with self.assertRaises(ValueError):
                api.synthesize("Hello.","A"*20,"ev")
            with self.assertRaises(ValueError):
                api.synthesize("Battery charge is low.","A"*20,"greeting")
            request.assert_not_called()

    def test_env_file_key_is_loaded_without_logging(self):
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            env = Path(d)/".env.local"
            env.write_text("OTHER=1\nELEVENLABS_API_KEY=fake-test-secret\n")
            with patch.dict(api.os.environ,{"ELEVENLABS_ENV_FILE":str(env)},clear=True), \
                    patch.object(api.urllib.request,"build_opener") as opener:
                response = opener.return_value.open.return_value.__enter__.return_value
                response.read.return_value = b'{"voices":[]}'
                api.request("/v1/shared-voices")
                request = opener.return_value.open.call_args.args[0]
                self.assertEqual(dict(request.header_items())["Xi-api-key"],"fake-test-secret")

    def test_loudness_normalisation_hits_rms_and_peak(self):
        samples = [10000,-10000]*500
        out,gain = normalise(samples,-16,-2)
        rms = math.sqrt(sum(x*x for x in out)/len(out))
        self.assertAlmostEqual(20*math.log10(rms/32768),-16,places=1)
        self.assertLessEqual(max(map(abs,out)),round(32768*10**(-2/20)))
        loud,gain2 = normalise([30000,-30000]*500,-16,-2)
        self.assertLessEqual(max(map(abs,loud)),round(32768*10**(-2/20)))
        self.assertLess(gain2,0)

    def test_generation_receipt_and_audio_integrity(self):
        raw = b"\0\0"*100
        data = wav_bytes(raw)
        meta = {"text":"Hello.","voice_id":"A"*20,"output_format":"pcm_22050",
                "wav_sha256":api.hashlib.sha256(data).hexdigest(),
                "pcm_sha256":api.hashlib.sha256(raw).hexdigest(),"frames":100}
        directory = Mock()
        p = Mock()
        directory.__truediv__ = Mock(return_value=p)
        p.read_bytes.return_value = data
        p.with_suffix.return_value.read_text.side_effect = lambda:json.dumps(meta)
        samples, voice, receipt = read_generated(directory,765,"Hello.")
        self.assertEqual((samples,voice),( [0]*100,"A"*20))
        self.assertEqual(receipt["wav_sha256"],meta["wav_sha256"])
        meta["text"] = "Other text."
        with self.assertRaisesRegex(ValueError,"receipt/hash mismatch"):
            read_generated(directory,765,"Hello.")


@unittest.skipUnless(SPEECH.exists(),"hash-pinned table fixture outside git unavailable")
class Encoder(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.tables = Tables(SPEECH.read_bytes())
        cls.sine = [round(12000*math.sin(2*math.pi*440*i/22050)) for i in range(4410)]

    def test_sine_roundtrip_and_delay(self):
        encoded = encode(self.sine,self.tables)
        decoded = decode(encoded,self.tables)
        self.assertGreater(snr(self.sine,decoded),30)
        self.assertEqual(len(decoded)//2,((len(self.sine)+127)//128+1)*128)

    def test_all_vector_modes_and_escape(self):
        # One of each mode repeated across bands; exact dequantised values checked.
        values = []
        scales = [0]*15
        peaks = (0,1,2,4,7,12,37)
        for band,(first,last) in enumerate(zip(self.tables.bands,self.tables.bands[1:])):
            p = peaks[band%len(peaks)]
            values.extend([(-p if j%2 else p) for j in range(last-first)])
        inv = {m:{symbol:pair for pair,symbol in codes.items()} for m,codes in self.tables.codes.items()}
        block = block_bits(scales,values,self.tables,inv)
        # Pad this one block only, with no end marker needed by coefficients().
        if block.count:
            block.put(0,8-block.count)
        observed = coefficients(Bits(bytes(block.data)),self.tables)
        expected = [(x if abs(x)<=1 else (1 if x>0 else -1)*(abs(x)*2-2))*1024 for x in values]
        self.assertEqual(observed,expected)

    def test_zero_roundtrip(self):
        self.assertFalse(any(decode(encode([0]*256,self.tables),self.tables)))

    def test_pcm_fit_and_quiet_trim(self):
        samples = [0]*1000+self.sine+[0]*1000
        trimmed,head,tail = quiet_trim(samples)
        self.assertGreater(head,0)
        self.assertGreater(tail,0)
        audio,fmt,_,meta = fit(samples,20000,self.tables)
        self.assertEqual(fmt.hex(),"02010102")
        self.assertEqual(meta["speed"],1)
        self.assertEqual(len(audio),len(trimmed)*2)

    def test_ssc_fit_within_budget(self):
        audio,fmt,_,meta = fit(self.sine,1800,self.tables)
        self.assertEqual(fmt.hex(),"02040102")
        self.assertLessEqual(len(audio),1800)
        self.assertGreaterEqual(meta["roundtrip_snr_db"],20)
        self.assertLessEqual(meta["speed"],1.12)


if __name__ == "__main__":
    unittest.main()
