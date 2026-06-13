"""MT3 (Google Magenta) transcription for polyphonic stems (guitar, piano).

This wraps the T5X-based MT3 model. The `InferenceModel` class is adapted from the
official MT3 inference colab (github.com/magenta/mt3, Apache-2.0) — the canonical way
to run MT3 inference, since the pip package exposes no high-level `predict()`.

Heavy + version-sensitive: depends on jax / t5x / t5 / seqio / note_seq / mt3. All of
that lives ONLY in the dedicated Modal `mt3_image` (see modal_app.py). Nothing on the
CPU base image or the local CLI imports this module, so its heavy top-level imports
never load there. The model is cached per (checkpoint, type) so warm containers reuse it.
"""
from __future__ import annotations

import functools
import os
from pathlib import Path

import gin
import jax
import librosa
import note_seq
import numpy as np
import seqio
import t5
import t5x
import tensorflow.compat.v2 as tf

from mt3 import metrics_utils, models, network, note_sequences, preprocessors, spectrograms, vocabularies

SAMPLE_RATE = 16000


def _gin_files(model_type: str) -> list[str]:
    """Locate the model + variant gin configs inside the installed mt3 package."""
    import mt3

    gin_dir = os.path.join(os.path.dirname(mt3.__file__), "gin")
    return [os.path.join(gin_dir, "model.gin"), os.path.join(gin_dir, f"{model_type}.gin")]


class InferenceModel:
    """T5X model wrapper for music transcription (adapted from the MT3 colab)."""

    def __init__(self, checkpoint_path: str, model_type: str = "mt3"):
        if model_type == "ismir2021":
            num_velocity_bins = 127
            self.encoding_spec = note_sequences.NoteEncodingSpec
            self.inputs_length = 512
        elif model_type == "mt3":
            num_velocity_bins = 1
            self.encoding_spec = note_sequences.NoteEncodingWithTiesSpec
            self.inputs_length = 256
        else:
            raise ValueError(f"unknown model_type: {model_type}")

        self.batch_size = 8
        self.outputs_length = 1024
        self.sequence_length = {"inputs": self.inputs_length, "targets": self.outputs_length}

        self.partitioner = t5x.partitioning.PjitPartitioner(num_partitions=1)
        self.spectrogram_config = spectrograms.SpectrogramConfig()
        self.codec = vocabularies.build_codec(
            vocab_config=vocabularies.VocabularyConfig(num_velocity_bins=num_velocity_bins)
        )
        self.vocabulary = vocabularies.vocabulary_from_codec(self.codec)
        self.output_features = {
            "inputs": seqio.ContinuousFeature(dtype=tf.float32, rank=2),
            "targets": seqio.Feature(vocabulary=self.vocabulary),
        }

        self._parse_gin(_gin_files(model_type))
        self.model = self._load_model()
        self.restore_from_checkpoint(checkpoint_path)

    @property
    def input_shapes(self):
        return {
            "encoder_input_tokens": (self.batch_size, self.inputs_length),
            "decoder_input_tokens": (self.batch_size, self.outputs_length),
        }

    def _parse_gin(self, gin_files):
        gin_bindings = [
            "from __gin__ import dynamic_registration",
            "from mt3 import vocabularies",
            "VOCAB_CONFIG=@vocabularies.VocabularyConfig()",
            "vocabularies.VocabularyConfig.num_velocity_bins=%NUM_VELOCITY_BINS",
        ]
        with gin.unlock_config():
            gin.parse_config_files_and_bindings(gin_files, gin_bindings, finalize_config=False)

    def _load_model(self):
        model_config = gin.get_configurable(network.T5Config)()
        module = network.Transformer(config=model_config)
        return models.ContinuousInputsEncoderDecoderModel(
            module=module,
            input_vocabulary=self.output_features["inputs"].vocabulary,
            output_vocabulary=self.output_features["targets"].vocabulary,
            optimizer_def=t5x.adafactor.Adafactor(decay_rate=0.8, step_offset=0),
            input_depth=spectrograms.input_depth(self.spectrogram_config),
        )

    def restore_from_checkpoint(self, checkpoint_path):
        train_state_initializer = t5x.utils.TrainStateInitializer(
            optimizer_def=self.model.optimizer_def,
            init_fn=self.model.get_initial_variables,
            input_shapes=self.input_shapes,
            partitioner=self.partitioner,
        )
        restore_checkpoint_cfg = t5x.utils.RestoreCheckpointConfig(
            path=checkpoint_path, mode="specific", dtype="float32"
        )
        train_state_axes = train_state_initializer.train_state_axes
        self._predict_fn = self._get_predict_fn(train_state_axes)
        self._train_state = train_state_initializer.from_checkpoint_or_scratch(
            [restore_checkpoint_cfg], init_rng=jax.random.PRNGKey(0)
        )

    @functools.lru_cache()
    def _get_predict_fn(self, train_state_axes):
        def partial_predict_fn(params, batch, decode_rng):
            return self.model.predict_batch_with_aux(params, batch, decoder_params={"decode_rng": None})

        return self.partitioner.partition(
            partial_predict_fn,
            in_axis_resources=(
                train_state_axes.params,
                t5x.partitioning.PartitionSpec("data"),
                None,
            ),
            out_axis_resources=t5x.partitioning.PartitionSpec("data"),
        )

    def predict_tokens(self, batch, seed=0):
        prediction, _ = self._predict_fn(self._train_state.params, batch, jax.random.PRNGKey(seed))
        return self.vocabulary.decode_tf(prediction).numpy()

    def __call__(self, audio):
        """Infer a NoteSequence from 16 kHz mono audio samples."""
        ds = self.audio_to_dataset(audio)
        ds = self.preprocess(ds)
        model_ds = self.model.FEATURE_CONVERTER_CLS(pack=False)(
            ds, task_feature_lengths=self.sequence_length
        )
        model_ds = model_ds.batch(self.batch_size)

        inferences = (
            tokens for batch in model_ds.as_numpy_iterator() for tokens in self.predict_tokens(batch)
        )
        predictions = []
        for example, tokens in zip(ds.as_numpy_iterator(), inferences):
            predictions.append(self.postprocess(tokens, example))

        result = metrics_utils.event_predictions_to_ns(
            predictions, codec=self.codec, encoding_spec=self.encoding_spec
        )
        return result["est_ns"]

    def audio_to_dataset(self, audio):
        frames, frame_times = self._audio_to_frames(audio)
        return tf.data.Dataset.from_tensors({"inputs": frames, "input_times": frame_times})

    def _audio_to_frames(self, audio):
        frame_size = self.spectrogram_config.hop_width
        padding = [0, frame_size - len(audio) % frame_size]
        audio = np.pad(audio, padding, mode="constant")
        frames = spectrograms.split_audio(audio, self.spectrogram_config)
        num_frames = len(audio) // frame_size
        times = np.arange(num_frames) / self.spectrogram_config.frames_per_second
        return frames, times

    def preprocess(self, ds):
        pp_chain = [
            functools.partial(
                t5.data.preprocessors.split_tokens_to_inputs_length,
                sequence_length=self.sequence_length,
                output_features=self.output_features,
                feature_key="inputs",
                additional_feature_keys=["input_times"],
            ),
            preprocessors.add_dummy_targets,
            functools.partial(
                preprocessors.compute_spectrograms, spectrogram_config=self.spectrogram_config
            ),
        ]
        for pp in pp_chain:
            ds = pp(ds)
        return ds

    def postprocess(self, tokens, example):
        tokens = self._trim_eos(tokens)
        start_time = example["input_times"][0]
        start_time -= start_time % (1 / self.codec.steps_per_second)
        return {"est_tokens": tokens, "start_time": start_time, "raw_inputs": []}

    @staticmethod
    def _trim_eos(tokens):
        tokens = np.array(tokens, np.int32)
        if vocabularies.DECODED_EOS_ID in tokens:
            tokens = tokens[: np.argmax(tokens == vocabularies.DECODED_EOS_ID)]
        return tokens


@functools.lru_cache(maxsize=2)
def _load(checkpoint_dir: str, model_type: str) -> InferenceModel:
    return InferenceModel(checkpoint_dir, model_type)


def transcribe_mt3(wav: Path, out_midi: Path, model_type: str, checkpoint_dir: str) -> Path:
    """Transcribe an isolated stem WAV to MIDI with MT3. Returns the MIDI path."""
    model = _load(checkpoint_dir, model_type)
    audio, _ = librosa.load(str(wav), sr=SAMPLE_RATE, mono=True)
    note_sequence = model(audio)
    out_midi.parent.mkdir(parents=True, exist_ok=True)
    note_seq.sequence_proto_to_midi_file(note_sequence, str(out_midi))
    return out_midi
