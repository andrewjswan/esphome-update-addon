% rebase('base.tpl', title='ESPHome Update Server')
<table>
  <thead>
  % for file, data in configs.items():
    <tr>
    % for key, value in data.items():
      % if key!='md5':
        % if key=='status':
        <th title="Status"></th>
        % else:
        <%
          key = key.upper().strip()
        %>
        <th>{{key}}</th>
        % end
      % end
    % end
    </tr>
  % break
  % end
  </thead>

  <tbody>
  % for file, data in configs.items():
    <tr>
    % for key, value in data.items():
      % if key!='md5':
        % if key=='http_ota':
          <td>
          % if value==True:
          <span class="online">
          % else:
          <span class="offline">
          % end
          </td>
        % elif key=='build':
          <td title="{{value}}">
          % if value==0:
          <span class="ok">
          % elif value<0:
          <span class="warning">
          % else:
          <span class="error">
          % end
          </td>
        % elif key=='file':
          <%
            value = value.split("/")[-1]
          %>
          <td><a href="config/{{value}}">{{value}}</a></td>
        % elif key=='status':
          <td title="{{value}}"><span class="{{value}}"></td>
        % elif key=='zzz':
          <%
            value = "complete" if value else "new"
          %>
          <td title="{{value}}"><span class="{{value}}"></td>
        % else:
          <td>{{value}}</td>
        % end
      % end
    % end
    </tr>
  % end
  </tbody>
</table>
