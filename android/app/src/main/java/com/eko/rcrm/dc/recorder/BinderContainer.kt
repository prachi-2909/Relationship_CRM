/*
 * Derived from CallVault (a fork of ShizuCallRecorder, Copyright (C) kitsumed (Med)),
 * GNU General Public License v3 or later. See recorder/_PORT_NOTICE.md.
 * Itself mirrors Shizuku-API's BinderContainer.
 */
package com.eko.rcrm.dc.recorder

import android.os.IBinder
import android.os.Parcel
import android.os.Parcelable

/** Wraps a live [IBinder] so it can ride inside a Bundle across a ContentProvider.call boundary -
 * writeStrongBinder/readStrongBinder is the only way to move an IBinder that way. */
class BinderContainer : Parcelable {
    @JvmField val binder: IBinder?

    constructor(binder: IBinder?) { this.binder = binder }
    private constructor(source: Parcel) { this.binder = source.readStrongBinder() }

    override fun describeContents(): Int = 0
    override fun writeToParcel(dest: Parcel, flags: Int) { dest.writeStrongBinder(binder) }

    companion object {
        @JvmField
        val CREATOR: Parcelable.Creator<BinderContainer> = object : Parcelable.Creator<BinderContainer> {
            override fun createFromParcel(source: Parcel) = BinderContainer(source)
            override fun newArray(size: Int): Array<BinderContainer?> = arrayOfNulls(size)
        }
    }
}
