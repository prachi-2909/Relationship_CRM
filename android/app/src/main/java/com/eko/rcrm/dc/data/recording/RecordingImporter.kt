package com.eko.rcrm.dc.data.recording

import android.content.Context
import android.net.Uri
import android.provider.DocumentsContract
import androidx.documentfile.provider.DocumentFile
import com.eko.rcrm.dc.data.local.RecordingFolderStore
import com.eko.rcrm.dc.data.local.db.PendingUploadKind
import com.eko.rcrm.dc.data.repository.CallRepository
import com.eko.rcrm.dc.domain.model.CallSession
import com.eko.rcrm.dc.util.Result
import dagger.hilt.android.qualifiers.ApplicationContext
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.withContext
import java.io.File
import javax.inject.Inject
import javax.inject.Singleton
import kotlin.math.abs

/** Bridges a call recorder that runs as its own app (e.g. ShizuCallRecorder, or a phone's built-in
 * recording) to a CRM call: finds the recording that belongs to a call, uploads it through the same
 * voice-note path (so it gets transcribed, briefed and reviewed like any other source), and then
 * deletes the file so the audio doesn't linger on the phone once it's in the CRM. The recorder
 * itself is never bundled or called into - this only reads files from a folder the DC picked. */
@Singleton
class RecordingImporter @Inject constructor(
    @ApplicationContext private val context: Context,
    private val folderStore: RecordingFolderStore,
    private val callRepository: CallRepository
) {
    sealed interface Outcome {
        data class Attached(val call: CallSession) : Outcome
        data object NoFolder : Outcome
        data object NotFound : Outcome
        data class Failed(val message: String) : Outcome
    }

    /** Looks in the chosen recordings folder for this call's recording and attaches it. */
    suspend fun attachFromFolder(call: CallSession): Outcome = withContext(Dispatchers.IO) {
        val uriString = folderStore.treeUri ?: return@withContext Outcome.NoFolder
        val tree = DocumentFile.fromTreeUri(context, Uri.parse(uriString))
        if (tree == null || !tree.canRead()) {
            return@withContext Outcome.Failed("Can't read the recordings folder any more - choose it again in Profile.")
        }
        val match = findMatch(tree, call) ?: return@withContext Outcome.NotFound
        upload(call, match.uri, match.name, deleteSource = { match.delete() })
    }

    /** Attaches a file the DC picked by hand, then tries to delete it too. Best-effort: whether
     * the picked document may be deleted is up to the app that owns it. */
    suspend fun attachPicked(call: CallSession, uri: Uri, displayName: String?): Outcome =
        withContext(Dispatchers.IO) {
            upload(call, uri, displayName, deleteSource = { DocumentsContract.deleteDocument(context.contentResolver, uri) })
        }

    /** Uploaded as a call recording, so the server applies the CRM-only rule to it - a recording
     * of a call with anyone who isn't a CRM official is refused and never stored. */
    private suspend fun upload(
        call: CallSession,
        source: Uri,
        name: String?,
        deleteSource: () -> Unit
    ): Outcome {
        val temp = File(context.cacheDir, "callrec_${call.id}.${uploadExtension(name)}")
        return try {
            context.contentResolver.openInputStream(source)?.use { input ->
                temp.outputStream().use { output -> input.copyTo(output) }
            } ?: return Outcome.Failed("Couldn't open the recording file.")
            if (temp.length() == 0L) return Outcome.Failed("The recording file is empty.")

            when (val result = callRepository.uploadVoiceNoteFile(call.id, temp, PendingUploadKind.CALL_RECORDING)) {
                is Result.Success -> {
                    runCatching { deleteSource() }
                    Outcome.Attached(result.data)
                }
                is Result.Error -> Outcome.Failed(result.message)
            }
        } catch (t: Throwable) {
            Outcome.Failed(t.message ?: "Couldn't read the recording file.")
        } finally {
            temp.delete()
        }
    }

    /** The backend picks the transcription format from the file extension, and doesn't know
     * ".oga"/".opus" (both are just Ogg audio), so those are uploaded as ".ogg". */
    private fun uploadExtension(name: String?): String {
        val ext = name?.substringAfterLast('.', "")?.lowercase().orEmpty()
        return when (ext) {
            "oga", "opus", "ogg" -> "ogg"
            "m4a", "mp3", "mp4", "wav", "flac", "webm" -> ext
            "aac", "3gp", "amr" -> "m4a"
            else -> "m4a"
        }
    }

    private fun findMatch(tree: DocumentFile, call: CallSession): DocumentFile? {
        val startMs = call.startedAtInstant?.toEpochMilli() ?: return null
        // A recording can only exist once the call is over.
        val endMs = call.endedAtInstant?.toEpochMilli() ?: return null
        val digits = call.phoneRef?.filter { it.isDigit() }?.takeLast(10).orEmpty()

        val inWindow = tree.listFiles().filter { file ->
            file.isFile && isAudio(file.name) &&
                file.lastModified() in (startMs - BEFORE_MS)..(endMs + AFTER_MS)
        }
        val numbered = if (digits.length >= 10) {
            inWindow.filter { it.name.orEmpty().filter { c -> c.isDigit() }.contains(digits) }
        } else emptyList()
        // Prefer a file whose name carries this call's number; with none, only trust the time
        // window when it narrows things down to a single file.
        val candidates = numbered.ifEmpty { if (inWindow.size == 1) inWindow else emptyList() }
        return candidates.minByOrNull { abs(it.lastModified() - endMs) }
    }

    private fun isAudio(name: String?): Boolean {
        val ext = name?.substringAfterLast('.', "")?.lowercase() ?: return false
        return ext in AUDIO_EXTENSIONS
    }

    private companion object {
        const val BEFORE_MS = 60_000L
        // Recorders can take a few seconds to finish writing after the call ends.
        const val AFTER_MS = 180_000L
        val AUDIO_EXTENSIONS = setOf("ogg", "oga", "opus", "m4a", "mp3", "wav", "aac", "amr", "3gp", "flac", "mp4", "webm")
    }
}
