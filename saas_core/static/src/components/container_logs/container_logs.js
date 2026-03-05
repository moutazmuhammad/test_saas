/** @odoo-module **/

import { Component, useState, useRef, onMounted, onWillUnmount } from "@odoo/owl";
import { registry } from "@web/core/registry";
import { useService } from "@web/core/utils/hooks";

class ContainerLogsStream extends Component {
    static template = "saas_core.ContainerLogsStream";
    static props = ["*"];

    setup() {
        this.action = useService("action");
        this.state = useState({
            lines: [],
            connected: false,
            error: null,
        });
        this.logRef = useRef("logContainer");
        this.eventSource = null;
        this.autoScroll = true;

        const { stream_url, container_name, tail } = this.props.action.context || {};
        this.streamUrl = stream_url;
        this.containerName = container_name || "Container";
        this.tail = tail || 100;

        onMounted(() => this.startStream());
        onWillUnmount(() => this.stopStream());
    }

    startStream() {
        this.stopStream();
        this.state.lines = [];
        this.state.error = null;
        this.state.connected = true;

        const url = `${this.streamUrl}?tail=${this.tail}`;
        this.eventSource = new EventSource(url);

        this.eventSource.onmessage = (event) => {
            const line = JSON.parse(event.data);
            this.state.lines.push(line);
            // Keep max 5000 lines in memory
            if (this.state.lines.length > 5000) {
                this.state.lines.splice(0, this.state.lines.length - 5000);
            }
            if (this.autoScroll) {
                this.scrollToBottom();
            }
        };

        this.eventSource.addEventListener("done", () => {
            this.state.connected = false;
            this.stopStream();
        });

        this.eventSource.addEventListener("error", (event) => {
            if (event.data) {
                this.state.error = JSON.parse(event.data);
            }
            this.state.connected = false;
            this.stopStream();
        });

        this.eventSource.onerror = () => {
            this.state.connected = false;
            this.stopStream();
        };
    }

    stopStream() {
        if (this.eventSource) {
            this.eventSource.close();
            this.eventSource = null;
        }
        this.state.connected = false;
    }

    scrollToBottom() {
        requestAnimationFrame(() => {
            const el = this.logRef.el;
            if (el) {
                el.scrollTop = el.scrollHeight;
            }
        });
    }

    onToggleAutoScroll() {
        this.autoScroll = !this.autoScroll;
        if (this.autoScroll) {
            this.scrollToBottom();
        }
    }

    onClear() {
        this.state.lines = [];
    }

    onReconnect() {
        this.startStream();
    }

    onStop() {
        this.stopStream();
    }

    get logText() {
        return this.state.lines.join("\n");
    }
}

registry.category("actions").add("container_logs_stream", ContainerLogsStream);
