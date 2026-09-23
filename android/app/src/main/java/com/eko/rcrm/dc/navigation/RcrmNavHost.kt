package com.eko.rcrm.dc.navigation

import androidx.compose.runtime.Composable
import androidx.compose.runtime.LaunchedEffect
import androidx.hilt.navigation.compose.hiltViewModel
import androidx.navigation.NavHostController
import androidx.navigation.NavType
import androidx.navigation.compose.NavHost
import androidx.navigation.compose.composable
import androidx.navigation.compose.rememberNavController
import androidx.navigation.navArgument
import com.eko.rcrm.dc.ui.history.CallHistoryScreen
import com.eko.rcrm.dc.ui.home.HomeScreen
import com.eko.rcrm.dc.ui.login.LoginScreen
import com.eko.rcrm.dc.ui.manualtext.ManualTextEntryScreen
import com.eko.rcrm.dc.ui.officialsearch.OfficialSearchScreen
import com.eko.rcrm.dc.ui.pending.PendingQueueScreen
import com.eko.rcrm.dc.ui.review.CallReviewScreen
import com.eko.rcrm.dc.ui.session.SessionViewModel
import com.eko.rcrm.dc.ui.voicenote.VoiceNoteRecordingScreen

private val callSessionIdArg = navArgument(Routes.CALL_REVIEW_ARG) { type = NavType.IntType }

@Composable
fun RcrmNavHost(navController: NavHostController = rememberNavController()) {
    val sessionViewModel: SessionViewModel = hiltViewModel()

    LaunchedEffect(Unit) {
        sessionViewModel.sessionExpired.collect {
            navController.navigate(Routes.LOGIN) {
                popUpTo(0) { inclusive = true }
                launchSingleTop = true
            }
        }
    }

    NavHost(navController = navController, startDestination = Routes.LOGIN) {

        composable(Routes.LOGIN) {
            LoginScreen(
                onLoginSuccess = {
                    navController.navigate(Routes.HOME) {
                        popUpTo(Routes.LOGIN) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.HOME) {
            HomeScreen(
                onSearchOfficials = { navController.navigate(Routes.OFFICIAL_SEARCH) },
                onPendingQueue = { navController.navigate(Routes.PENDING_QUEUE) },
                onCallHistory = { navController.navigate(Routes.CALL_HISTORY) },
                onLoggedOut = {
                    navController.navigate(Routes.LOGIN) {
                        popUpTo(0) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.OFFICIAL_SEARCH) {
            OfficialSearchScreen(
                onBack = { navController.popBackStack() },
                onCallStarted = { callSessionId ->
                    navController.navigate(Routes.callReview(callSessionId)) {
                        popUpTo(Routes.OFFICIAL_SEARCH) { inclusive = true }
                    }
                }
            )
        }

        composable(Routes.PENDING_QUEUE) {
            PendingQueueScreen(
                onBack = { navController.popBackStack() },
                onOpenCall = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) }
            )
        }

        composable(Routes.CALL_HISTORY) {
            CallHistoryScreen(
                onBack = { navController.popBackStack() },
                onOpenCall = { callSessionId -> navController.navigate(Routes.callReview(callSessionId)) }
            )
        }

        composable(Routes.CALL_REVIEW, arguments = listOf(callSessionIdArg)) {
            CallReviewScreen(
                onBack = { navController.popBackStack() },
                onRecordVoiceNote = { callSessionId -> navController.navigate(Routes.voiceNoteRecording(callSessionId)) },
                onManualTextEntry = { callSessionId -> navController.navigate(Routes.manualTextEntry(callSessionId)) },
                onDone = {
                    val popped = navController.popBackStack(Routes.HOME, inclusive = false)
                    if (!popped) {
                        navController.navigate(Routes.HOME) { popUpTo(0) { inclusive = true } }
                    }
                }
            )
        }

        composable(Routes.VOICE_NOTE_RECORDING, arguments = listOf(callSessionIdArg)) {
            VoiceNoteRecordingScreen(
                onBack = { navController.popBackStack() },
                onSaved = { navController.popBackStack() }
            )
        }

        composable(Routes.MANUAL_TEXT_ENTRY, arguments = listOf(callSessionIdArg)) {
            ManualTextEntryScreen(
                onBack = { navController.popBackStack() },
                onSaved = { navController.popBackStack() }
            )
        }
    }
}
