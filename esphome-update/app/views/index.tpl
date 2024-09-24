% rebase('base.tpl', title='ESPHome Update Server')
<table>
  <thead>
  % for file, data in configs.items():
    <tr>
    % for key, value in data.items():
      % if key!='md5':
      <%
        key = key.upper().strip()
      %>
      <td>{{key}}</td>
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
          % if value==True:
          <td><span class="online"></td>
          % else:
          <td><span class="offline"></td>
          % end
        % else:
          % if key=='build':
            % if value==0:
            <td><span class="ok"></td>
            % else:
              % if value<0:
              <td><span class="warning"></td>
              % else:
              <td><span class="error"></td>
              % end
            % end
          % else:
          <td>{{value}}</td>
          % end
        % end
      % end
    % end
    </tr>
  % end
  </tbody>
</table>
